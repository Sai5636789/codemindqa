"""
Q&A Chain — Step 6 of the pipeline.

WHAT IT DOES:
  - Takes a user question + retrieved code chunks
  - Sends them to Meta LLaMA 3 via Groq API
  - Returns a structured answer with:
      * The answer text (markdown formatted)
      * Citations (file path, lines, function name for each source)
      * Which model was used and token count

WHY GROQ + LLAMA 3:
  - Groq's hardware (LPU) runs LLaMA 3 at ~500 tokens/sec — almost as fast
    as GPT-4 but completely FREE on the Groq developer tier.
  - llama3-70b-8192 rivals GPT-4 for coding tasks.
  - 8192 token context window is large enough to fit 5-7 code chunks + history.

RAG PROMPT DESIGN:
  The system prompt is carefully crafted to:
  1. PREVENT hallucination ("only use the provided code context")
  2. ENFORCE citations ("always cite file paths and line numbers")
  3. FORMAT for readability (markdown code blocks, step-by-step for flows)
  4. ACKNOWLEDGE uncertainty ("say I don't know if not in context")

CONVERSATIONAL MEMORY:
  We maintain a sliding window of the last 5 messages (user + assistant).
  For follow-up questions like "what about its parameters?", LLaMA 3 can
  refer back to the previous answer (which mentioned the function) and
  correctly understand the implicit reference.
"""

import os
import logging
from typing import List, Dict, Optional
from dotenv import load_dotenv
from groq import Groq

logger = logging.getLogger("qa_chain")

# Fetch from environment
GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")
LLAMA_MODEL = os.getenv("LLAMA_MODEL", "llama-3.3-70b-versatile")

SYSTEM_PROMPT = """You are an expert code documentation assistant.
Answer based ONLY on the provided code context. Always cite file paths and line numbers.
If not in context, say you don't know."""

class QAChain:
    def __init__(self):
        load_dotenv()
        api_key = os.getenv("GROQ_API_KEY", "").strip()
        model = os.getenv("LLAMA_MODEL", "llama-3.3-70b-versatile")

        if not api_key or api_key == "your_groq_api_key_here":
            logger.error("GROQ_API_KEY is missing from environment.")
            raise ValueError("GROQ_API_KEY is missing.")

        # Initialize DIRECT Groq client
        self.client = Groq(api_key=api_key)
        self.memories: Dict[str, List] = {}
        logger.info(f"QAChain (Direct) initialized with model {model}")

    def ask(self, question: str, context: str, session_id: str = "default", retrieved_chunks: Optional[List[Dict]] = None) -> Dict:
        history = self._get_history(session_id)
        
        # Build messages for direct Groq call
        messages = [{"role": "system", "content": SYSTEM_PROMPT}]
        # Add history
        for msg in history:
            messages.append({"role": msg["role"], "content": msg["content"]})
        
        # Add current question with context
        messages.append({
            "role": "user", 
            "content": f"Context:\n{context}\n\nQuestion: {question}"
        })

        logger.info(f"Direct API call to Groq for session {session_id}...")
        try:
            completion = self.client.chat.completions.create(
                model=LLAMA_MODEL,
                messages=messages,
                temperature=0.1,
                max_tokens=2048,
            )
            answer = completion.choices[0].message.content
            logger.info("Direct Groq API success.")
        except Exception as e:
            logger.error(f"Direct Groq API error: {e}")
            raise

        # Update memory
        self._add_to_history(session_id, "user", question)
        self._add_to_history(session_id, "assistant", answer)

        # Citations
        citations = []
        if retrieved_chunks:
            for chunk in retrieved_chunks:
                meta = chunk.get("metadata", {})
                citations.append({
                    "file": meta.get("relative_path", ""),
                    "start_line": meta.get("start_line", ""),
                    "end_line": meta.get("end_line", ""),
                    "function": meta.get("function_name", ""),
                    "class_": meta.get("class_name", ""),
                    "score": chunk.get("score", 0),
                })

        return {
            "answer": answer,
            "citations": citations,
            "model": LLAMA_MODEL,
            "session_id": session_id,
        }

    def _get_history(self, session_id: str) -> List:
        if session_id not in self.memories: self.memories[session_id] = []
        return self.memories[session_id][-10:]

    def _add_to_history(self, session_id: str, role: str, content: str):
        if session_id not in self.memories: self.memories[session_id] = []
        self.memories[session_id].append({"role": role, "content": content})

    def clear_session(self, session_id: str):
        """Clear conversation history for a session."""
        self.memories.pop(session_id, None)

    def list_sessions(self) -> List[str]:
        return list(self.memories.keys())
