"""
GitHub Loader — Step 1 of the pipeline.

WHAT IT DOES:
  - Takes a GitHub URL (e.g. https://github.com/user/repo)
  - Clones the repo locally using GitPython
  - Walks every file in the repo
  - Returns only code files (filters out binaries, node_modules, etc.)

WHY WE DO THIS:
  We need the raw source code on disk so tree-sitter can parse it.
  GitPython is a thin Python wrapper around git, so it handles auth,
  shallow clones, etc. without us shelling out to subprocess.

EXPLANATION OF KEY CHOICES:
  - EXCLUDED_DIRS: these directories contain generated/dependency code
    that would massively inflate the index without adding value.
  - CODE_EXTENSIONS: we only parse files that have a known grammar.
    Binary or config files can't be meaningfully chunked into code units.
  - Shallow clone (depth=1): we only want the latest snapshot, not full
    git history. This dramatically reduces clone time for large repos.
"""

import os
import shutil
from pathlib import Path
from typing import List, Dict
import git
from dotenv import load_dotenv

load_dotenv()

# Directories we skip — they contain 3rd-party or generated code
EXCLUDED_DIRS = {
    "node_modules", ".git", "venv", ".venv", "env",
    "__pycache__", ".pytest_cache", "build", "dist",
    "target", ".gradle", "vendor", ".next", "out",
    "coverage", ".nyc_output", "eggs", "*.egg-info"
}

# We only parse files with these extensions (tree-sitter grammars available)
CODE_EXTENSIONS = {
    ".py": "python",
    ".js": "javascript",
    ".jsx": "javascript",
    ".ts": "typescript",
    ".tsx": "typescript",
    ".java": "java",
    ".go": "go",
    ".c": "c",
    ".h": "c",
    ".cpp": "cpp",
    ".hpp": "cpp",
    ".cc": "cpp",
    ".cxx": "cpp",
    ".cs": "c_sharp",
    ".rs": "rust",
    ".rb": "ruby",
    ".php": "php",
    ".kt": "kotlin",
    ".kts": "kotlin",
    ".swift": "swift",
    ".html": "html",
    ".css": "css",
    ".sql": "sql",
    ".ipynb": "jupyter",
}


class GitHubLoader:
    """
    Clones a GitHub repository and returns a list of parseable code files.

    Usage:
        loader = GitHubLoader(repos_dir="./data/repos")
        files = loader.load("https://github.com/pallets/flask", "flask")
        # files = [{"path": "/abs/path/to/file.py", "language": "python", ...}, ...]
    """

    def __init__(self, repos_dir: str = None):
        self.repos_dir = Path(repos_dir or os.getenv("REPOS_DIR", "./data/repos"))
        self.repos_dir.mkdir(parents=True, exist_ok=True)

    def load(self, repo_url: str, repo_name: str, github_pat: str = None) -> List[Dict]:
        """
        Clone (or reuse cached) repo and return list of code file metadata.

        Args:
            repo_url: Full GitHub URL, e.g. https://github.com/pallets/flask
            repo_name: Short identifier used as local directory name

        Returns:
            List of dicts: {path, language, relative_path, repo_name, size_bytes}
        """
        clone_path = self.repos_dir / repo_name
        
        # Inject PAT if provided
        auth_url = repo_url
        if github_pat and "github.com" in repo_url:
            auth_url = repo_url.replace("https://github.com", f"https://{github_pat}@github.com")

        # If repo already cloned, pull latest changes instead of skipping
        if clone_path.exists():
            print(f"[Loader] Repo '{repo_name}' already exists. Pulling latest changes...")
            try:
                repo = git.Repo(clone_path)
                origin = repo.remotes.origin
                origin.set_url(auth_url)
                origin.pull()
            except Exception as e:
                print(f"[Loader] Error pulling '{repo_name}': {e}. Proceeding with existing code.")
            repo_path = clone_path
        else:
            print(f"[Loader] Cloning {repo_url} → {clone_path}")
            # depth=1 = shallow clone (only latest commit, much faster)
            try:
                git.Repo.clone_from(auth_url, clone_path, depth=1)
            except Exception as e:
                print(f"[Loader] Clone failed: {e}")
                raise e
            repo_path = clone_path

        return self._collect_files(repo_path, repo_name)

    def _collect_files(self, repo_path: Path, repo_name: str) -> List[Dict]:
        """Walk the repo and collect all parseable code files."""
        files = []

        for root, dirs, filenames in os.walk(repo_path):
            # Prune excluded directories IN-PLACE so os.walk won't descend into them
            # This is the standard os.walk pruning pattern
            dirs[:] = [d for d in dirs if d not in EXCLUDED_DIRS and not d.startswith(".")]

            for filename in filenames:
                ext = Path(filename).suffix.lower()
                if ext not in CODE_EXTENSIONS:
                    continue

                abs_path = os.path.join(root, filename)
                rel_path = os.path.relpath(abs_path, repo_path)
                size = os.path.getsize(abs_path)

                # Skip huge generated files (e.g. minified JS bundles)
                if size > 200_000:  # 200KB limit
                    continue

                files.append({
                    "path": abs_path,
                    "relative_path": rel_path,
                    "language": CODE_EXTENSIONS[ext],
                    "repo_name": repo_name,
                    "filename": filename,
                    "extension": ext,
                    "size_bytes": size,
                })

        print(f"[Loader] Found {len(files)} code files in '{repo_name}'")
        return files

    def delete_repo(self, repo_name: str):
        """Remove a cloned repository from disk."""
        clone_path = self.repos_dir / repo_name
        if clone_path.exists():
            shutil.rmtree(clone_path)
            print(f"[Loader] Deleted repo '{repo_name}'")
