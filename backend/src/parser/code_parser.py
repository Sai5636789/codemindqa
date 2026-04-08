"""
Code Parser — Step 2 of the pipeline.

WHAT IT DOES:
  - Given a source file + its language, parses it with tree-sitter
  - Extracts:
      * Every function definition (name, docstring, params, start/end lines, body)
      * Every class definition (name, methods, start/end lines)
      * All import statements grouped

WHY WE USE TREE-SITTER:
  tree-sitter builds a real Abstract Syntax Tree (AST) from source code.
  This is far more accurate than regex: it handles nested functions, string
  literals with def/class keywords inside them, decorated functions, etc.
  It parses code the same way a compiler does.

WHY THIS MATTERS FOR RAG:
  The quality of your chunks depends entirely on how well you identify
  "meaningful units" of code. A function is the atomic unit of code logic.
  Splitting a function across two chunks creates a useless, broken chunk.
  tree-sitter ensures we never split at bad boundaries.

IMPORTANT NOTE ON tree-sitter v0.21:
  In tree-sitter 0.21, you load language grammars via Language.build_library()
  or from pre-built wheels. We use the pre-built wheels (tree-sitter-python etc.)
  which expose a `language()` function directly.
"""

import os
import json
from pathlib import Path
from typing import List, Dict, Optional
from tree_sitter import Language, Parser
import tree_sitter_python as tspython
import tree_sitter_javascript as tsjavascript
import tree_sitter_java as tsjava
import tree_sitter_go as tsgo
import tree_sitter_c as tsc
import tree_sitter_cpp as tscpp
import tree_sitter_rust as tsrust
import tree_sitter_ruby as tsruby
import tree_sitter_php as tsphp
import tree_sitter_kotlin as tskotlin
import tree_sitter_swift as tsswift
import tree_sitter_html as tshtml
import tree_sitter_css as tscss
import tree_sitter_sql as tssql

# ---------------------------------------------------------------------------
# Load grammars from pre-built wheel packages
# Each language module exposes a language() function returning a Language object
# ---------------------------------------------------------------------------
PY_LANGUAGE = Language(tspython.language())
JS_LANGUAGE = Language(tsjavascript.language())
JAVA_LANGUAGE = Language(tsjava.language())
GO_LANGUAGE = Language(tsgo.language())
C_LANGUAGE = Language(tsc.language())
CPP_LANGUAGE = Language(tscpp.language())
RUST_LANGUAGE = Language(tsrust.language())
RUBY_LANGUAGE = Language(tsruby.language())
PHP_LANGUAGE = Language(tsphp.language_php())
KOTLIN_LANGUAGE = Language(tskotlin.language())
SWIFT_LANGUAGE = Language(tsswift.language())
HTML_LANGUAGE = Language(tshtml.language())
CSS_LANGUAGE = Language(tscss.language())
SQL_LANGUAGE = Language(tssql.language())

# TypeScript uses the JavaScript grammar for JSX, with a separate TS grammar
try:
    import tree_sitter_typescript as tsts
    TS_LANGUAGE = Language(tsts.language_typescript())
    TSX_LANGUAGE = Language(tsts.language_tsx())
except Exception:
    # Fallback: use JS grammar for TS files if TS grammar unavailable
    TS_LANGUAGE = JS_LANGUAGE
    TSX_LANGUAGE = JS_LANGUAGE

LANGUAGE_MAP: Dict[str, Language] = {
    "python": PY_LANGUAGE,
    "javascript": JS_LANGUAGE,
    "typescript": TS_LANGUAGE,
    "java": JAVA_LANGUAGE,
    "go": GO_LANGUAGE,
    "c": C_LANGUAGE,
    "cpp": CPP_LANGUAGE,
    "rust": RUST_LANGUAGE,
    "ruby": RUBY_LANGUAGE,
    "php": PHP_LANGUAGE,
    "kotlin": KOTLIN_LANGUAGE,
    "swift": SWIFT_LANGUAGE,
    "html": HTML_LANGUAGE,
    "css": CSS_LANGUAGE,
    "sql": SQL_LANGUAGE,
}


class CodeParser:
    """
    Parses source code files using tree-sitter and extracts functions, classes,
    and imports as structured dictionaries.

    Usage:
        parser = CodeParser()
        result = parser.parse_file("/path/to/file.py", "python")
        print(result["functions"])  # list of function dicts
        print(result["classes"])    # list of class dicts
    """

    def __init__(self):
        # One Parser instance can be reused across files (just swap the language)
        self.parser = Parser()

    def parse_file(self, file_path: str, language: str) -> Dict:
        """
        Main entry point. Parse a single file and return extracted structure.

        Returns:
            {
              "functions": [...],  # top-level functions
              "classes":   [...],  # classes with nested methods
              "imports":   [...],  # all import strings
              "file_summary": str, # first module docstring if present
            }
        """
        lang_grammar = LANGUAGE_MAP.get(language)
        if not lang_grammar:
            return {"functions": [], "classes": [], "imports": [], "file_summary": ""}

        try:
            source = Path(file_path).read_bytes()  # bytes — tree-sitter works on bytes
        except (IOError, OSError):
            return {"functions": [], "classes": [], "imports": [], "file_summary": ""}

        self.parser.language = lang_grammar
        tree = self.parser.parse(source)

        root = tree.root_node
        source_str = source.decode("utf-8", errors="replace")

        if language == "python":
            result = self._extract_python(root, source_str)
        elif language in ("javascript", "typescript"):
            result = self._extract_js(root, source_str)
        elif language == "java":
            result = self._extract_java(root, source_str)
        elif language == "go":
            result = self._extract_go(root, source_str)
        elif language == "jupyter":
            result = self._extract_jupyter(file_path)
        elif language in ("c", "cpp", "rust", "ruby", "php", "kotlin", "swift", "html", "css", "sql"):
            result = self._extract_generic(root, source_str, language)
        else:
            result = {"functions": [], "classes": [], "imports": [], "file_summary": ""}

        if not result["functions"] and not result["classes"]:
            # FALLBACK: If no functions/classes found, treat the whole file as one large "function"
            # This ensures SQL, Text, or simple scripts are still indexed.
            result["functions"].append({
                "name": "Global Scope / File Content",
                "class_name": "",
                "docstring": "",
                "params": [],
                "start_line": 1,
                "end_line": len(source_str.split("\n")),
                "body": source_str,
                "chunk_type": "function",
            })

        return result

    # ------------------------------------------------------------------
    # PYTHON EXTRACTOR
    # Python AST node types: function_definition, class_definition,
    # import_statement, import_from_statement, expression_statement(string)
    # ------------------------------------------------------------------
    def _extract_python(self, root, source: str) -> Dict:
        functions = []
        classes = []
        imports = []
        file_summary = ""

        for node in root.children:
            node_type = node.type

            # Module-level docstring (first string literal at top level)
            if node_type == "expression_statement" and not file_summary:
                text = self._node_text(node, source).strip().strip('"').strip("'")
                if len(text) > 10:
                    file_summary = text[:500]

            elif node_type == "function_definition":
                functions.append(self._extract_py_function(node, source))

            elif node_type == "class_definition":
                classes.append(self._extract_py_class(node, source))

            elif node_type in ("import_statement", "import_from_statement"):
                imports.append(self._node_text(node, source).strip())

        return {
            "functions": functions,
            "classes": classes,
            "imports": imports,
            "file_summary": file_summary,
        }

    def _extract_py_function(self, node, source: str, class_name: str = "") -> Dict:
        """Extract a Python function: name, docstring, params, start/end lines, body."""
        name = ""
        docstring = ""
        params = []

        for child in node.children:
            if child.type == "identifier":
                name = self._node_text(child, source)
            elif child.type == "parameters":
                # Collect parameter names (skip self, cls)
                for p in child.children:
                    if p.type == "identifier":
                        pname = self._node_text(p, source)
                        if pname not in ("self", "cls"):
                            params.append(pname)
            elif child.type == "block":
                # First child of block that is an expression_statement containing a string = docstring
                for stmt in child.children:
                    if stmt.type == "expression_statement":
                        text = self._node_text(stmt, source).strip()
                        if (text.startswith('"""') or text.startswith("'''") or
                                text.startswith('"') or text.startswith("'")):
                            docstring = text.strip('"').strip("'")[:300]
                        break

        body_text = self._node_text(node, source)
        return {
            "name": name,
            "class_name": class_name,
            "docstring": docstring,
            "params": params,
            "start_line": node.start_point[0] + 1,   # tree-sitter is 0-indexed
            "end_line": node.end_point[0] + 1,
            "body": body_text,
            "chunk_type": "function",
        }

    def _extract_py_class(self, node, source: str) -> Dict:
        """Extract a Python class: name, docstring, and all its methods."""
        name = ""
        docstring = ""
        methods = []

        for child in node.children:
            if child.type == "identifier":
                name = self._node_text(child, source)
            elif child.type == "block":
                # Check first stmt for class docstring
                first = True
                for stmt in child.children:
                    if first and stmt.type == "expression_statement":
                        text = self._node_text(stmt, source).strip()
                        if text.startswith('"""') or text.startswith("'"):
                            docstring = text.strip('"').strip("'")[:300]
                        first = False
                    if stmt.type == "function_definition":
                        methods.append(self._extract_py_function(stmt, source, class_name=name))

        return {
            "name": name,
            "docstring": docstring,
            "methods": methods,
            "start_line": node.start_point[0] + 1,
            "end_line": node.end_point[0] + 1,
            "body": self._node_text(node, source),
            "chunk_type": "class",
        }

    # ------------------------------------------------------------------
    # JAVASCRIPT / TYPESCRIPT EXTRACTOR
    # Node types: function_declaration, arrow_function, class_declaration,
    # method_definition, import_statement, export_statement, ...
    # ------------------------------------------------------------------
    def _extract_js(self, root, source: str) -> Dict:
        functions = []
        classes = []
        imports = []

        def walk(node, class_name=""):
            t = node.type
            if t in ("function_declaration", "function_expression"):
                name = ""
                for c in node.children:
                    if c.type == "identifier":
                        name = self._node_text(c, source)
                        break
                functions.append({
                    "name": name or "anonymous",
                    "class_name": class_name,
                    "docstring": "",
                    "params": [],
                    "start_line": node.start_point[0] + 1,
                    "end_line": node.end_point[0] + 1,
                    "body": self._node_text(node, source),
                    "chunk_type": "function",
                })
            elif t in ("arrow_function",):
                # Arrow functions are usually assigned to variables
                # The parent variable_declarator has the name
                pass
            elif t == "class_declaration":
                class_name_local = ""
                class_methods = []
                for c in node.children:
                    if c.type == "identifier":
                        class_name_local = self._node_text(c, source)
                    elif c.type == "class_body":
                        for m in c.children:
                            if m.type == "method_definition":
                                mname = ""
                                for mc in m.children:
                                    if mc.type == "property_identifier":
                                        mname = self._node_text(mc, source)
                                class_methods.append({
                                    "name": mname,
                                    "class_name": class_name_local,
                                    "docstring": "",
                                    "params": [],
                                    "start_line": m.start_point[0] + 1,
                                    "end_line": m.end_point[0] + 1,
                                    "body": self._node_text(m, source),
                                    "chunk_type": "function",
                                })
                classes.append({
                    "name": class_name_local,
                    "docstring": "",
                    "methods": class_methods,
                    "start_line": node.start_point[0] + 1,
                    "end_line": node.end_point[0] + 1,
                    "body": self._node_text(node, source),
                    "chunk_type": "class",
                })
            elif t in ("import_statement", "import_declaration"):
                imports.append(self._node_text(node, source).strip())

            for child in node.children:
                walk(child, class_name)

        walk(root)
        return {"functions": functions, "classes": classes, "imports": imports, "file_summary": ""}

    # ------------------------------------------------------------------
    # JAVA EXTRACTOR (simplified)
    # ------------------------------------------------------------------
    def _extract_java(self, root, source: str) -> Dict:
        functions = []
        classes = []
        imports = []

        def walk(node, class_name=""):
            t = node.type
            if t == "import_declaration":
                imports.append(self._node_text(node, source).strip())
            elif t == "class_declaration":
                cname = ""
                methods = []
                for c in node.children:
                    if c.type == "identifier":
                        cname = self._node_text(c, source)
                    elif c.type == "class_body":
                        for m in c.children:
                            if m.type == "method_declaration":
                                mname = ""
                                for mc in m.children:
                                    if mc.type == "identifier":
                                        mname = self._node_text(mc, source)
                                        break
                                methods.append({
                                    "name": mname,
                                    "class_name": cname,
                                    "docstring": "",
                                    "params": [],
                                    "start_line": m.start_point[0] + 1,
                                    "end_line": m.end_point[0] + 1,
                                    "body": self._node_text(m, source),
                                    "chunk_type": "function",
                                })
                classes.append({
                    "name": cname,
                    "docstring": "",
                    "methods": methods,
                    "start_line": node.start_point[0] + 1,
                    "end_line": node.end_point[0] + 1,
                    "body": self._node_text(node, source),
                    "chunk_type": "class",
                })
            else:
                for child in node.children:
                    walk(child, class_name)

        walk(root)
        return {"functions": functions, "classes": classes, "imports": imports, "file_summary": ""}

    # ------------------------------------------------------------------
    # GO EXTRACTOR
    # ------------------------------------------------------------------
    def _extract_go(self, root, source: str) -> Dict:
        functions = []
        imports = []

        def walk(node):
            t = node.type
            if t == "function_declaration":
                name = ""
                for c in node.children:
                    if c.type == "identifier":
                        name = self._node_text(c, source)
                        break
                functions.append({
                    "name": name,
                    "class_name": "",
                    "docstring": "",
                    "params": [],
                    "start_line": node.start_point[0] + 1,
                    "end_line": node.end_point[0] + 1,
                    "body": self._node_text(node, source),
                    "chunk_type": "function",
                })
            elif t == "method_declaration":
                # Go methods have receivers: func (r *Receiver) MethodName()
                name = ""
                receiver = ""
                for c in node.children:
                    if c.type == "field_identifier" or c.type == "identifier":
                        name = self._node_text(c, source)
                    elif c.type == "parameter_list" and not receiver:
                        # This is the receiver list if it's the first parameter_list
                        receiver = self._node_text(c, source)
                
                # Try to extract just the type name from the receiver
                receiver_name = ""
                if receiver:
                    # Very simple extraction: (r *MyType) -> MyType
                    receiver_name = receiver.strip("()").split()[-1].strip("*")

                functions.append({
                    "name": name,
                    "class_name": receiver_name,
                    "docstring": "",
                    "params": [],
                    "start_line": node.start_point[0] + 1,
                    "end_line": node.end_point[0] + 1,
                    "body": self._node_text(node, source),
                    "chunk_type": "function",
                })
            elif t == "import_declaration":
                imports.append(self._node_text(node, source).strip())

            for child in node.children:
                walk(child)

        walk(root)
        return {"functions": functions, "classes": [], "imports": imports, "file_summary": ""}

    # ------------------------------------------------------------------
    # GENERIC EXTRACTOR (C, C++, Rust, etc.)
    # ------------------------------------------------------------------
    def _extract_generic(self, root, source: str, language: str) -> Dict:
        """
        Generic extractor for languages that follow common patterns:
        - Functions: function_definition, function_item, declaration
        - Classes: class_specifier, struct_specifier, impl_item
        """
        functions = []
        classes = []
        imports = []

        # Common node types to look for
        func_types = {
            "function_definition", "function_item", "method_declaration", "declaration",
            "rule_set", "element", # For CSS/HTML
            "create_table_statement", "create_view_statement", "create_index_statement",
            "create_procedure_definition", "create_function_definition" # For SQL
        }
        class_types = {"class_specifier", "struct_specifier", "impl_item", "mod_item"}
        imp_types = {"preproc_include", "use_declaration", "import_declaration", "import_statement"}

        def walk(node):
            t = node.type
            if t in func_types:
                # Try to find an identifier for the name
                name = "anonymous"
                for c in node.children:
                    if c.type in ("identifier", "field_identifier", "type_identifier", "selectors", "start_tag", "object_reference"):
                        name = self._node_text(c, source)
                        break
                functions.append({
                    "name": name,
                    "class_name": "",
                    "docstring": "",
                    "params": [],
                    "start_line": node.start_point[0] + 1,
                    "end_line": node.end_point[0] + 1,
                    "body": self._node_text(node, source),
                    "chunk_type": "function",
                })
            elif t in class_types:
                # Structs/Classes
                name = "anonymous"
                for c in node.children:
                    if c.type in ("identifier", "type_identifier"):
                        name = self._node_text(c, source)
                        break
                classes.append({
                    "name": name,
                    "docstring": "",
                    "methods": [],
                    "start_line": node.start_point[0] + 1,
                    "end_line": node.end_point[0] + 1,
                    "body": self._node_text(node, source),
                    "chunk_type": "class",
                })
            elif t in imp_types:
                imports.append(self._node_text(node, source).strip())
            
            # Recurse if not a function body (to find nested things if any)
            if t not in func_types:
                for child in node.children:
                    walk(child)

        walk(root)
        return {"functions": functions, "classes": classes, "imports": imports, "file_summary": ""}

    def _extract_jupyter(self, file_path: str) -> Dict:
        """Extract code cells from a .ipynb (Jupyter Notebook) file."""
        functions = []
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                nb = json.load(f)
            
            # Simple approach: each code cell is a "function"
            for i, cell in enumerate(nb.get("cells", [])):
                if cell.get("cell_type") == "code":
                    source = "".join(cell.get("source", []))
                    if source.strip():
                        functions.append({
                            "name": f"Cell {i+1}",
                            "class_name": "Jupyter Notebook",
                            "docstring": "",
                            "params": [],
                            "start_line": 1, 
                            "end_line": len(source.split("\n")),
                            "body": source,
                            "chunk_type": "function",
                        })
        except Exception as e:
            logger.error(f"Error parsing Jupyter notebook: {e}")

        return {"functions": functions, "classes": [], "imports": [], "file_summary": "Jupyter Notebook file"}

    def _node_text(self, node, source: str) -> str:
        """Extract the exact text of a node from the full source string."""
        start_byte = node.start_byte
        end_byte = node.end_byte
        # Convert to char positions (source is a string, not bytes here)
        # We use line/column to avoid byte vs char offset issues with unicode
        lines = source.split("\n")
        start_line, start_col = node.start_point
        end_line, end_col = node.end_point
        if start_line == end_line:
            return lines[start_line][start_col:end_col]
        result = [lines[start_line][start_col:]]
        for i in range(start_line + 1, end_line):
            if i < len(lines):
                result.append(lines[i])
        if end_line < len(lines):
            result.append(lines[end_line][:end_col])
        return "\n".join(result)
