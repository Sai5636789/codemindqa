"""
Code Chunker — Step 3 of the pipeline.

WHAT IT DOES:
  Converts parsed code structures (functions, classes, imports) into
  "chunks" — small, self-contained text units ready for embedding.

WHY SMART CHUNKING MATTERS:
  Naive approaches (split every N characters) break code in bad places:
  - Middle of a function body → the chunk has no context
  - Between method and its docstring → the docstring becomes useless

  Our approach: ONE FUNCTION = ONE CHUNK
  This preserves the atomic unit of meaning in code.

CHUNK TYPES:
  1. "function"     → a single function or method body
  2. "class_header" → class name + docstring (gives class-level context)
  3. "file_header"  → imports + module docstring (gives file-level context)

ENRICHMENT (the key to good retrieval):
  Before creating the embedding text, we add a structured prefix:
    File: src/auth/middleware.py | Language: python
    Type: function | Name: authenticate_user | Class: AuthMiddleware
    Docstring: Validates JWT and attaches user to request
  This prefix is included in the embedding so semantic search understands
  WHAT the chunk is, not just what text it contains.
"""

from typing import List, Dict
import tiktoken


# Token counter — we use cl100k_base (same as GPT-4's tokenizer)
# as a proxy for counting tokens. It's not exact for LLaMA, but close enough.
try:
    _enc = tiktoken.get_encoding("cl100k_base")
    def count_tokens(text: str) -> int:
        return len(_enc.encode(text))
except Exception:
    def count_tokens(text: str) -> int:
        return len(text.split()) * 4 // 3  # rough fallback


MAX_CHUNK_TOKENS = 800   # Aim to keep chunks under this size
OVERLAP_CHARS = 200      # Character overlap between consecutive chunks if we must split


class CodeChunker:
    """
    Takes the output of CodeParser and produces a flat list of chunks,
    each ready to be embedded and stored in ChromaDB.

    Usage:
        chunker = CodeChunker()
        chunks = chunker.chunk_file(parsed_result, file_meta)
    """

    def chunk_file(self, parsed: Dict, file_meta: Dict) -> List[Dict]:
        """
        Convert one file's parsed result into a list of chunk dicts.

        Args:
            parsed: Output of CodeParser.parse_file()
            file_meta: Dict with {path, relative_path, language, repo_name, filename}

        Returns:
            List of chunk dicts, each with {text, embedding_text, metadata}
        """
        chunks = []

        # ---- CHUNK 1: File Header (imports + module docstring) ----------------
        # This chunk answers "what does this file do and what does it import?"
        if parsed["imports"] or parsed["file_summary"]:
            header_text = ""
            if parsed["file_summary"]:
                header_text += f'"""{parsed["file_summary"]}"""\n\n'
            if parsed["imports"]:
                header_text += "\n".join(parsed["imports"])

            if header_text.strip():
                chunks.append(self._build_chunk(
                    code_text=header_text,
                    chunk_type="file_header",
                    function_name="",
                    class_name="",
                    file_meta=file_meta,
                    start_line=1,
                    end_line=len(parsed["imports"]) + 3,
                    docstring=parsed["file_summary"],
                ))

        # ---- CHUNK 2: Top-level functions ----------------------------------------
        # Each function becomes its own chunk. If a function is huge (>MAX tokens),
        # we split it at a character boundary and add overlap so context isn't lost.
        for func in parsed["functions"]:
            func_chunks = self._chunk_code_unit(func, file_meta)
            chunks.extend(func_chunks)

        # ---- CHUNK 3: Classes ------------------------------------------------
        # We create TWO kinds of class chunks:
        # a) A "class_header" chunk with just the class definition and docstring
        # b) Individual method chunks (same as function chunks)
        for cls in parsed["classes"]:
            # 3a: Class header
            class_header_text = f"class {cls['name']}:\n"
            if cls["docstring"]:
                class_header_text += f'    """{cls["docstring"]}"""\n'
            if class_header_text.strip():
                chunks.append(self._build_chunk(
                    code_text=class_header_text,
                    chunk_type="class_header",
                    function_name="",
                    class_name=cls["name"],
                    file_meta=file_meta,
                    start_line=cls["start_line"],
                    end_line=cls["start_line"] + 3,
                    docstring=cls["docstring"],
                ))

            # 3b: Individual methods
            for method in cls["methods"]:
                # Inherit class_name in the method metadata
                method["class_name"] = cls["name"]
                method_chunks = self._chunk_code_unit(method, file_meta)
                chunks.extend(method_chunks)

        return chunks

    def _chunk_code_unit(self, unit: Dict, file_meta: Dict) -> List[Dict]:
        """
        Given a function or method dict, produce one or more chunks.
        If the unit is <= MAX_CHUNK_TOKENS, it's one chunk.
        If larger, split it and add overlap between parts.
        """
        body = unit.get("body", "")
        token_count = count_tokens(body)

        if token_count <= MAX_CHUNK_TOKENS:
            # ✅ Common case: small enough to be one chunk
            return [self._build_chunk(
                code_text=body,
                chunk_type=unit.get("chunk_type", "function"),
                function_name=unit.get("name", ""),
                class_name=unit.get("class_name", ""),
                file_meta=file_meta,
                start_line=unit.get("start_line", 0),
                end_line=unit.get("end_line", 0),
                docstring=unit.get("docstring", ""),
            )]

        # Large function: split at line boundaries every ~MAX_CHUNK_TOKENS tokens
        # We keep a signature header in every sub-chunk for context
        lines = body.split("\n")
        signature = lines[0] if lines else ""  # "def function_name(args):"
        sub_chunks = []
        current_lines = [signature]  # start each part with the function signature

        for line in lines[1:]:
            current_lines.append(line)
            if count_tokens("\n".join(current_lines)) > MAX_CHUNK_TOKENS:
                # Save current sub-chunk and start a new one with overlap
                chunk_text = "\n".join(current_lines[:-1])
                sub_chunks.append(chunk_text)
                # Overlap: redo last OVERLAP_CHARS characters in next chunk
                current_lines = [signature] + current_lines[-5:]  # keep last 5 lines

        if current_lines:
            sub_chunks.append("\n".join(current_lines))

        result = []
        for idx, sub_text in enumerate(sub_chunks):
            result.append(self._build_chunk(
                code_text=sub_text,
                chunk_type=unit.get("chunk_type", "function"),
                function_name=f"{unit.get('name', '')} (part {idx+1}/{len(sub_chunks)})",
                class_name=unit.get("class_name", ""),
                file_meta=file_meta,
                start_line=unit.get("start_line", 0),
                end_line=unit.get("end_line", 0),
                docstring=unit.get("docstring", ""),
            ))
        return result

    def _build_chunk(
        self,
        code_text: str,
        chunk_type: str,
        function_name: str,
        class_name: str,
        file_meta: Dict,
        start_line: int,
        end_line: int,
        docstring: str,
    ) -> Dict:
        """
        Build the final chunk dict. Most importantly, construct two text fields:

        - text: the raw code (stored in ChromaDB, returned to the LLM as context)
        - embedding_text: enriched version used ONLY for embedding
          (file path + type + name + docstring + code)

        WHY TWO TEXTS?
          The embedding text has extra context that helps the vector search find
          relevant code. But we don't want to feed all that boilerplate to the LLM
          when generating the answer — we just send clean code.
        """
        rel_path = file_meta.get("relative_path", "")
        language = file_meta.get("language", "")
        repo_name = file_meta.get("repo_name", "")

        # Structured prefix for embedding
        prefix_parts = [
            f"File: {rel_path}",
            f"Language: {language}",
            f"Type: {chunk_type}",
        ]
        if class_name:
            prefix_parts.append(f"Class: {class_name}")
        if function_name:
            prefix_parts.append(f"Function: {function_name}")
        if docstring:
            prefix_parts.append(f"Description: {docstring[:200]}")

        prefix = " | ".join(prefix_parts)
        embedding_text = f"{prefix}\n\n{code_text}"

        return {
            "text": code_text,                    # what LLM sees
            "embedding_text": embedding_text,     # what gets embedded
            "metadata": {
                "repo_name": repo_name,
                "file_path": file_meta.get("path", ""),
                "relative_path": rel_path,
                "filename": file_meta.get("filename", ""),
                "language": language,
                "chunk_type": chunk_type,
                "function_name": function_name,
                "class_name": class_name,
                "start_line": start_line,
                "end_line": end_line,
                "docstring": docstring[:200] if docstring else "",
            },
        }
