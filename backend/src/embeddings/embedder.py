"""
Embedder — Step 4 of the pipeline.

WHAT IT DOES:
  - Initializes a ChromaDB vector store with persistence
  - Takes code chunks and embeds them using a free HuggingFace model
  - Stores vectors + metadata in ChromaDB for later retrieval

WHY HUGGINGFACE EMBEDDINGS (not OpenAI):
  - Free: no API key, no cost. Runs locally.
  - sentence-transformers/all-MiniLM-L6-v2 is a battle-tested model
    that produces high-quality 384-dim vectors.
  - Specifically fine-tuned for semantic similarity — perfect for our use case.
  - First run: downloads ~90MB model. Subsequent runs use cache.

WHY CHROMADB:
  - Zero-configuration. No Docker, no server required.
  - Persists to disk so vectors survive restarts.
  - Supports metadata filtering (e.g., "only search Python files").
  - Fast enough for 100K+ documents.
  - One-command setup vs. Qdrant's Docker requirement.

COLLECTION NAMING:
  We use one ChromaDB collection per repository. This lets us:
  - Search a specific repo without cross-contamination
  - Delete a repo's data cleanly
  - Show "indexed repos" in the UI
"""

import os
from typing import List, Dict
from pathlib import Path
from dotenv import load_dotenv
import chromadb
from chromadb.config import Settings
from sentence_transformers import SentenceTransformer

load_dotenv()

CHROMA_PERSIST_DIR = os.getenv("CHROMA_PERSIST_DIR", "./data/chroma")
EMBEDDING_MODEL_NAME = "sentence-transformers/all-MiniLM-L6-v2"
BATCH_SIZE = 64  # embed this many chunks at a time to avoid memory issues


class Embedder:
    """
    Manages the embedding model and ChromaDB vector store.

    Usage:
        embedder = Embedder()
        embedder.index_chunks(chunks, repo_name="flask")
        results = embedder.search("how does routing work?", repo_name="flask", k=5)
    """

    def __init__(self):
        # Load the embedding model once (cached after first download)
        print(f"[Embedder] Loading embedding model: {EMBEDDING_MODEL_NAME}")
        self.model = SentenceTransformer(EMBEDDING_MODEL_NAME)
        print("[Embedder] Model loaded.")

        # Initialize ChromaDB with disk persistence
        Path(CHROMA_PERSIST_DIR).mkdir(parents=True, exist_ok=True)
        self.client = chromadb.PersistentClient(path=CHROMA_PERSIST_DIR)

    def _get_or_create_collection(self, repo_name: str):
        """
        Get or create a ChromaDB collection for a specific repo.
        Collection name = "repo_{repo_name}" (must be alphanumeric + underscores).
        """
        # Sanitize repo name for ChromaDB collection naming rules
        safe_name = "repo_" + "".join(c if c.isalnum() else "_" for c in repo_name)
        return self.client.get_or_create_collection(
            name=safe_name,
            metadata={"hnsw:space": "cosine"},  # cosine similarity for semantic search
        )

    def index_chunks(self, chunks: List[Dict], repo_name: str) -> int:
        """
        Embed and store all chunks for a repository.

        Args:
            chunks:    List of chunk dicts from CodeChunker
            repo_name: Repository identifier used as collection key

        Returns:
            Number of chunks successfully indexed
        """
        collection = self._get_or_create_collection(repo_name)

        # Get existing IDs to avoid re-indexing duplicates
        existing = collection.get(include=[])
        existing_ids = set(existing["ids"])

        # Prepare data, filtering duplicates
        new_chunks = []
        for i, chunk in enumerate(chunks):
            # Chunk ID = deterministic from relative path + start_line
            chunk_id = f"{chunk['metadata']['relative_path']}::{chunk['metadata']['start_line']}::{i}"
            if chunk_id not in existing_ids:
                chunk["id"] = chunk_id
                new_chunks.append(chunk)

        if not new_chunks:
            print(f"[Embedder] All {len(chunks)} chunks already indexed for '{repo_name}'")
            return 0

        print(f"[Embedder] Indexing {len(new_chunks)} new chunks for '{repo_name}'...")

        # Process in batches
        total = 0
        for batch_start in range(0, len(new_chunks), BATCH_SIZE):
            batch = new_chunks[batch_start: batch_start + BATCH_SIZE]

            # Embed the ENRICHED text (prefix + code) for better retrieval
            texts_to_embed = [c["embedding_text"] for c in batch]
            embeddings = self.model.encode(texts_to_embed, show_progress_bar=False).tolist()

            # ChromaDB expects parallel lists
            ids = [c["id"] for c in batch]
            documents = [c["text"] for c in batch]  # raw code stored as document
            metadatas = [c["metadata"] for c in batch]

            collection.add(
                ids=ids,
                embeddings=embeddings,
                documents=documents,
                metadatas=metadatas,
            )
            total += len(batch)
            print(f"[Embedder]   {total}/{len(new_chunks)} chunks indexed")

        print(f"[Embedder] ✅ Done. {total} chunks stored for '{repo_name}'")
        return total

    def search(
        self,
        query: str,
        repo_name: str,
        k: int = 7,
        filters: Dict = None,
    ) -> List[Dict]:
        """
        Semantic similarity search over a repo's collection.

        Args:
            query:     The user's question or search string
            repo_name: Which repo collection to search
            k:         Number of results to return
            filters:   Optional ChromaDB where-filter, e.g. {"language": "python"}

        Returns:
            List of result dicts: {text, metadata, score}
        """
        collection = self._get_or_create_collection(repo_name)

        # Embed the query using the same model used to embed chunks
        query_embedding = self.model.encode([query]).tolist()[0]

        where_clause = filters if filters else None

        results = collection.query(
            query_embeddings=[query_embedding],
            n_results=min(k, collection.count()),  # can't request more than we have
            where=where_clause,
            include=["documents", "metadatas", "distances"],
        )

        # Reformat results into a flat list of dicts
        output = []
        if results["ids"] and results["ids"][0]:
            for i, doc_id in enumerate(results["ids"][0]):
                # ChromaDB returns L2 distance; convert to similarity score
                # For cosine (our collection metric), distance = 1 - similarity
                distance = results["distances"][0][i]
                similarity = 1.0 - distance  # 1.0 = perfect match, 0.0 = unrelated
                output.append({
                    "id": doc_id,
                    "text": results["documents"][0][i],
                    "metadata": results["metadatas"][0][i],
                    "score": round(similarity, 4),
                })

        return output

    def list_repos(self) -> List[str]:
        """Return all indexed repo names."""
        collections = self.client.list_collections()
        repos = []
        for col in collections:
            if col.name.startswith("repo_"):
                # Strip the "repo_" prefix
                repos.append(col.name[5:])
        return repos

    def delete_repo(self, repo_name: str) -> bool:
        """Delete all indexed data for a repository."""
        safe_name = "repo_" + "".join(c if c.isalnum() else "_" for c in repo_name)
        try:
            self.client.delete_collection(safe_name)
            print(f"[Embedder] Deleted collection for '{repo_name}'")
            return True
        except Exception as e:
            print(f"[Embedder] Could not delete '{repo_name}': {e}")
            return False

    def collection_stats(self, repo_name: str) -> Dict:
        """Return stats about a repo's collection (count, sample metadata)."""
        collection = self._get_or_create_collection(repo_name)
        count = collection.count()
        return {"chunk_count": count, "repo_name": repo_name}
