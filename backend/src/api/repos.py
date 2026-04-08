import logging
from typing import Optional, Dict
from datetime import datetime
from fastapi import APIRouter, BackgroundTasks, HTTPException, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session
import uuid

from ..db.database import get_db
from ..db.models import User, Repository
from ..auth.auth_bearer import get_current_user

# Pipeline modules
from ..parser.github_loader import GitHubLoader
from ..parser.code_parser import CodeParser
from ..chunker.code_chunker import CodeChunker
from ..embeddings.embedder import Embedder

logger = logging.getLogger("api")
router = APIRouter(prefix="/api/repos", tags=["Repositories"])

loader = GitHubLoader()
parser = CodeParser()
chunker = CodeChunker()
embedder = Embedder()

indexing_jobs: Dict[str, Dict] = {}

class IndexRequest(BaseModel):
    repo_url: str
    repo_name: str
    github_pat: Optional[str] = None

@router.post("/index")
async def index_repository(request: IndexRequest, background_tasks: BackgroundTasks, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    """Trigger indexing of a GitHub repository for the current user."""
    repo_name = request.repo_name.strip().replace(" ", "_").lower()
    
    if not request.repo_url.startswith("https://github.com"):
        raise HTTPException(status_code=400, detail="Only GitHub URLs are supported.")

    # Check if repo already exists for user
    repo = db.query(Repository).filter(Repository.user_id == current_user.id, Repository.repo_name == repo_name).first()
    
    if not repo:
        repo = Repository(
            id=str(uuid.uuid4()),
            user_id=current_user.id,
            repo_name=repo_name,
            repo_url=request.repo_url,
            github_pat=request.github_pat,
            is_private=bool(request.github_pat)
        )
        db.add(repo)
        db.commit()
    elif request.github_pat:
        repo.github_pat = request.github_pat
        db.commit()

    # Create composite name to isolate users in ChromaDB
    collection_name = f"{current_user.id}_{repo_name}"

    indexing_jobs[collection_name] = {
        "status": "running",
        "started_at": datetime.now().isoformat(),
        "repo_url": request.repo_url,
        "files_processed": 0,
        "chunks_indexed": 0,
        "error": None,
    }

    background_tasks.add_task(_run_indexing_pipeline, request.repo_url, collection_name, repo.id, request.github_pat)

    return {
        "message": f"Indexing started for '{repo_name}'",
        "repo_name": repo_name,
        "status": "running",
    }

def _run_indexing_pipeline(repo_url: str, collection_name: str, db_repo_id: str, github_pat: Optional[str]):
    """Background task: The full indexing pipeline (Incremental supported if folder exists)."""
    try:
        job = indexing_jobs[collection_name]
        job["status"] = "cloning/pulling"

        # 1. Clone / Pull files (Loader needs update to handle PATs and diffs, passing dummy for now)
        files = loader.load(repo_url, collection_name, github_pat=github_pat)
        
        # Incremental logic: if we wanted pure incremental, loader would return only changed files.
        # But this requires more Git logic. For MVP incremental, overwrite the collection for now,
        # but the db schema is ready to track commit hashes later.

        job["status"] = "parsing"
        job["total_files"] = len(files)

        all_chunks = []
        for i, file_meta in enumerate(files):
            try:
                parsed = parser.parse_file(file_meta["path"], file_meta["language"])
                chunks = chunker.chunk_file(parsed, file_meta)
                all_chunks.extend(chunks)
            except Exception as e:
                logger.exception(f"[Indexer] Skipping {file_meta['path']}")
                continue

            job["files_processed"] = i + 1
            job["status"] = f"parsing ({i+1}/{len(files)} files)"

        job["status"] = "embedding"
        
        # If full re-index, delete existing vectors first
        embedder.delete_repo(collection_name)
        total_indexed = embedder.index_chunks(all_chunks, collection_name)
        job["chunks_indexed"] = total_indexed

        # Update DB on success
        from ..db.database import SessionLocal
        db = SessionLocal()
        try:
            repo = db.query(Repository).filter(Repository.id == db_repo_id).first()
            if repo:
                repo.last_indexed_at = datetime.utcnow()
                db.commit()
        finally:
            db.close()

        job["status"] = "done"
        job["completed_at"] = datetime.now().isoformat()
        logger.info(f"[Indexer] '{collection_name}' indexed: {len(files)} files, {total_indexed} chunks")

    except Exception as e:
        logger.exception(f"[Indexer] Error indexing '{collection_name}'")
        if collection_name in indexing_jobs:
            indexing_jobs[collection_name]["status"] = "error"
            indexing_jobs[collection_name]["error"] = str(e)

@router.get("")
def list_repos(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    """List all indexed repositories for the current user."""
    db_repos = db.query(Repository).filter(Repository.user_id == current_user.id).all()
    result = []
    
    for repo in db_repos:
        collection_name = f"{current_user.id}_{repo.repo_name}"
        job = indexing_jobs.get(collection_name, {})
        
        # Get actual chunk count from ChromaDB
        try:
            stats = embedder.collection_stats(collection_name)
            chunk_count = stats.get("chunk_count", 0)
            status = "done"
        except Exception:
            chunk_count = 0
            status = job.get("status", "error")
            
        if job.get("status") in ["running", "cloning/pulling", "parsing", "embedding"]:
            status = job["status"]

        result.append({
            "name": repo.repo_name,
            "chunk_count": chunk_count,
            "status": status,
            "indexed_at": str(repo.last_indexed_at) if repo.last_indexed_at else job.get("completed_at", ""),
            "repo_url": repo.repo_url,
            "is_private": repo.is_private,
            "files_processed": job.get("files_processed", 0),
            "error": job.get("error"),
        })
    return {"repos": result}

@router.delete("/{repo_name}")
def delete_repo(repo_name: str, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    """Remove a repository from the database and vector store."""
    repo = db.query(Repository).filter(Repository.user_id == current_user.id, Repository.repo_name == repo_name).first()
    if not repo:
        raise HTTPException(status_code=404, detail="Repository not found")

    collection_name = f"{current_user.id}_{repo_name}"
    embedder.delete_repo(collection_name)
    loader.delete_repo(collection_name)
    indexing_jobs.pop(collection_name, None)
    
    db.delete(repo)
    db.commit()
    return {"message": f"Repository '{repo_name}' deleted successfully."}
