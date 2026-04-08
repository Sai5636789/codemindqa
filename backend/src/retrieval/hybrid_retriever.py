"""
Hybrid Retriever — Step 5 of the pipeline.

WHAT IT DOES:
  Combines two complementary retrieval strategies:
  1. Semantic Search  (via ChromaDB embeddings)  — weight 0.7
  2. Keyword Search   (via BM25 algorithm)        — weight 0.3

WHY HYBRID IS ESSENTIAL FOR CODE:

  Semantic alone fails for:
    - "Where is `authenticate_user` defined?" — it knows conceptually what auth
      is, but might retrieve docs about auth rather than that specific function
    - Exact method/variable names that aren't in the embedding's vocabulary

  Keyword alone fails for:
    - "How does the user registration flow work?" — no single keyword captures this
    - Synonyms: "login" vs "authenticate" vs "sign_in"

  HYBRID FORMULA:
    final_score = 0.7 * semantic_score + 0.3 * bm25_score

  This automatically gives the best of both worlds for any query type.

BM25 (Best Match 25):
  BM25 is a probabilistic keyword ranking algorithm that outperforms TF-IDF.
  It penalizes very long documents (prevents long files from dominating) and
  uses IDF (inverse document frequency) to downweight common terms.
  rank-bm25 library implements this efficiently.
"""

import re
import logging
from typing import List, Dict, Optional
from rank_bm25 import BM25Okapi
from src.embeddings.embedder import Embedder

logger = logging.getLogger("hybrid_retriever")

SEMANTIC_WEIGHT = 0.7
KEYWORD_WEIGHT = 0.3


class HybridRetriever:
    """
    Retrieves the most relevant code chunks using hybrid semantic + BM25 search.

    Usage:
        retriever = HybridRetriever(embedder)
        results = retriever.retrieve("How does authentication work?", repo_name="flask")
    """

    def __init__(self, embedder: Embedder):
        self.embedder = embedder

    def retrieve(
        self,
        query: str,
        repo_name: str,
        k: int = 5,
        top_k_candidate: int = 20,
        filters: Optional[Dict] = None,
    ) -> List[Dict]:
        """
        Main retrieval method. Returns top-k chunks sorted by hybrid score.

        Steps:
          1. Get top 20 results from semantic search (broad net)
          2. Run BM25 on those same 20 chunks using the query
          3. Combine scores with SEMANTIC_WEIGHT + KEYWORD_WEIGHT weighting
          4. Sort by final score, return top k

        Args:
            query:            User's question
            repo_name:        Which repo to search
            k:                How many results to return
            top_k_candidate:  How many semantic results to initially fetch
            filters:          Optional ChromaDB metadata filter (e.g. {"language": "python"})

        Returns:
            List of result dicts (sorted by hybrid score, descending)
        """
        # ---- STEP 1: Broad semantic search -----------------------------------
        logger.info(f"Retrieving top {top_k_candidate} semantic candidates for repo '{repo_name}'...")
        semantic_results = self.embedder.search(
            query=query,
            repo_name=repo_name,
            k=top_k_candidate,
            filters=filters,
        )

        if not semantic_results:
            return []

        # Create semantic score lookup: chunk_id → score
        semantic_scores = {r["id"]: r["score"] for r in semantic_results}

        # ---- STEP 2: BM25 on the candidate set --------------------------------
        logger.info(f"Running BM25 reranking on {len(semantic_results)} candidates...")
        # Tokenize all candidate texts + the query
        corpus = [self._tokenize(r["text"]) for r in semantic_results]
        bm25 = BM25Okapi(corpus)
        query_tokens = self._tokenize(query)
        bm25_raw_scores = bm25.get_scores(query_tokens)

        # Normalize BM25 scores to [0, 1] so they're comparable to semantic scores
        max_bm25 = max(bm25_raw_scores) if max(bm25_raw_scores) > 0 else 1.0
        bm25_normalized = [s / max_bm25 for s in bm25_raw_scores]

        # ---- STEP 3: Combine scores ------------------------------------------
        hybrid_results = []
        for i, result in enumerate(semantic_results):
            sem_score = semantic_scores[result["id"]]
            kw_score = bm25_normalized[i]
            final_score = SEMANTIC_WEIGHT * sem_score + KEYWORD_WEIGHT * kw_score

            hybrid_results.append({
                **result,  # copy all original fields
                "semantic_score": round(sem_score, 4),
                "keyword_score": round(kw_score, 4),
                "score": round(final_score, 4),  # overwrite with hybrid score
            })

        # ---- STEP 4: Sort and return top k ------------------------------------
        hybrid_results.sort(key=lambda x: x["score"], reverse=True)
        top_k = hybrid_results[:k]
        logger.info(f"Hybrid retrieval complete. Top score: {top_k[0]['score'] if top_k else 'N/A'}")
        return top_k

    def _tokenize(self, text: str) -> List[str]:
        """
        Simple tokenizer for BM25.
        Splits on non-alphanumeric characters (handles camelCase, snake_case,
        and code symbols) and lowercases for case-insensitive matching.
        """
        # Split camelCase: "authenticateUser" → "authenticate User"
        text = re.sub(r"([a-z])([A-Z])", r"\1 \2", text)
        # Replace non-alphanumeric with space
        tokens = re.sub(r"[^a-zA-Z0-9]", " ", text).lower().split()
        # Remove very short tokens and Python/JS keywords (they add noise)
        stop = {"def", "class", "return", "if", "else", "for", "while",
                 "import", "from", "const", "let", "var", "function", "self"}
        return [t for t in tokens if len(t) > 1 and t not in stop]

    def format_context(self, results: List[Dict]) -> str:
        """
        Format retrieved chunks into a single context string for the LLM.
        Each chunk includes: file path, line numbers, language, and code.

        The LLM uses this to generate its answer and citations.
        """
        if not results:
            return "No relevant code found."

        context_parts = []
        for i, result in enumerate(results):
            meta = result.get("metadata", {})
            rel_path = meta.get("relative_path", "unknown")
            start = meta.get("start_line", "?")
            end = meta.get("end_line", "?")
            lang = meta.get("language", "")
            chunk_type = meta.get("chunk_type", "code")
            fn_name = meta.get("function_name", "")
            cls_name = meta.get("class_name", "")

            header = f"[{i+1}] {rel_path} (lines {start}-{end})"
            if cls_name:
                header += f" | Class: {cls_name}"
            if fn_name:
                header += f" | Function: {fn_name}"

            code_block = f"```{lang}\n{result['text']}\n```"
            context_parts.append(f"{header}\n{code_block}")

        return "\n\n---\n\n".join(context_parts)
