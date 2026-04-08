import logging
from typing import Optional, Dict
from datetime import datetime
from fastapi import APIRouter, BackgroundTasks, HTTPException, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session
import traceback
import uuid

from ..db.database import get_db
from ..db.models import User, Repository, ChatSession, ChatMessage
from ..auth.auth_bearer import get_current_user

# Pipeline modules
from ..parser.github_loader import GitHubLoader
from ..parser.code_parser import CodeParser
from ..chunker.code_chunker import CodeChunker
from ..embeddings.embedder import Embedder
from ..retrieval.hybrid_retriever import HybridRetriever
from ..qa.qa_chain import QAChain

logger = logging.getLogger("api")
router = APIRouter(prefix="/api/chat", tags=["Q&A"])

# Lazily instantiated components
embedder = Embedder()
retriever = HybridRetriever(embedder)
_qa_chain: Optional[QAChain] = None

def get_qa_chain() -> QAChain:
    global _qa_chain
    if _qa_chain is None:
        _qa_chain = QAChain()
    return _qa_chain

class ChatRequest(BaseModel):
    question: str
    repo_name: str
    session_id: Optional[str] = None
    filters: Optional[Dict] = None

@router.post("")
def chat(request: ChatRequest, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    """Ask a question about an indexed repository."""
    repo = db.query(Repository).filter(Repository.user_id == current_user.id, Repository.repo_name == request.repo_name).first()
    if not repo:
        raise HTTPException(status_code=404, detail="Repository not found or you do not have permission.")

    logger.info(f"User {current_user.username} asking about repo '{repo.repo_name}': {request.question[:50]}...")
    
    # Prepend user ID to repo_name for the ChromaDB collection namespace
    collection_name = f"{current_user.id}_{repo.repo_name}"

    try:
        # 1. Retrieve
        retrieved = retriever.retrieve(
            query=request.question,
            repo_name=collection_name, 
            k=5,
            filters=request.filters,
        )

        session_id = request.session_id
        if not session_id:
            # Create a new session in DB
            chat_session = ChatSession(
                id=str(uuid.uuid4()),
                user_id=current_user.id,
                repo_id=repo.id,
                title=request.question[:30] + "..."
            )
            db.add(chat_session)
            db.commit()
            db.refresh(chat_session)
            session_id = chat_session.id
        else:
            # Validate session belongs to user
            chat_session = db.query(ChatSession).filter(ChatSession.id == session_id, ChatSession.user_id == current_user.id).first()
            if not chat_session:
                 raise HTTPException(status_code=404, detail="Chat session not found")

        # Save user message to DB
        user_msg = ChatMessage(session_id=session_id, role="user", content=request.question)
        db.add(user_msg)
        db.commit()

        if not retrieved:
            answer = "I couldn't find any relevant code in the repository. Make sure the repository is fully indexed."
            bot_msg = ChatMessage(session_id=session_id, role="assistant", content=answer, citations="[]")
            db.add(bot_msg)
            db.commit()
            return {
                "answer": answer,
                "citations": [],
                "chunks_retrieved": 0,
                "session_id": session_id,
            }

        # Format and Ask LLM
        context = retriever.format_context(retrieved)
        qa = get_qa_chain()
        
        # Load past messages to reconstruct conversation context conceptually
        # Note: A full implementation would pipe history into the LangChain prompt template
        past_msgs = db.query(ChatMessage).filter(ChatMessage.session_id == session_id).order_by(ChatMessage.created_at).all()
        history = [(m.role, m.content) for m in past_msgs]

        response = qa.ask(
            question=request.question,
            context=context,
            session_id=session_id,
            retrieved_chunks=retrieved,
        )
        
        # Save bot message
        import json
        bot_msg = ChatMessage(
            session_id=session_id, 
            role="assistant", 
            content=response["answer"],
            citations=json.dumps(response.get("citations", []))
        )
        db.add(bot_msg)
        db.commit()

        return {
            **response,
            "chunks_retrieved": len(retrieved),
            "session_id": session_id
        }

    except Exception as e:
        logger.exception(f"Error in chat endpoint for repo '{request.repo_name}'")
        raise HTTPException(
            status_code=500, 
            detail=f"Internal Server Error: {str(e)}\n{traceback.format_exc()}"
        )

@router.get("/history/{repo_name}")
def get_chat_history(repo_name: str, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    """Fetch all past chat sessions and messages for a specific repo and user."""
    repo = db.query(Repository).filter(Repository.user_id == current_user.id, Repository.repo_name == repo_name).first()
    if not repo:
        raise HTTPException(status_code=404, detail="Repository not found.")

    sessions = db.query(ChatSession).filter(ChatSession.repo_id == repo.id).order_by(ChatSession.created_at.desc()).all()
    
    result = []
    import json
    for session in sessions:
        msgs = [{"role": msg.role, "content": msg.content, "citations": json.loads(msg.citations) if msg.citations else []} for msg in session.messages]
        result.append({
            "session_id": session.id,
            "title": session.title,
            "created_at": session.created_at,
            "messages": msgs
        })
    return {"history": result}
