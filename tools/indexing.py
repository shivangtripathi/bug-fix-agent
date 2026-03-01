from __future__ import annotations

import ast
import hashlib
import logging
import os
from pathlib import Path
from typing import Any

import chromadb
from chromadb.utils import embedding_functions

logger = logging.getLogger(__name__)

# Directories to skip while walking the repository tree
_SKIP_DIRS = {
    ".git",
    "__pycache__",
    ".mypy_cache",
    ".pytest_cache",
    ".tox",
    ".venv",
    "venv",
    "env",
    "node_modules",
    "dist",
    "build",
    ".chroma",
}

# Skip directories that look like virtualenvs (contain pyvenv.cfg)
def _is_venv(path: Path) -> bool:
    return (path / "pyvenv.cfg").exists()


def _iter_python_files(repo_root: Path):
    """Yield all .py files under repo_root, skipping common noise directories."""
    for dirpath, dirnames, filenames in os.walk(repo_root):
        current = Path(dirpath)
        # Prune skip-dirs in-place so os.walk doesn't recurse into them
        dirnames[:] = [
            d for d in dirnames
            if d not in _SKIP_DIRS and not _is_venv(current / d)
        ]
        for fname in filenames:
            if fname.endswith(".py"):
                yield current / fname


def _chunk_file(file_path: Path, repo_root: Path) -> list[dict[str, Any]]:
    """
    Split a Python source file into chunks at top-level function/class boundaries.
    Falls back to one whole-file chunk if parsing fails or the file is empty.

    Each chunk dict:
        file       – path relative to repo_root (POSIX string)
        start_line – 1-indexed line where the chunk starts
        snippet    – the source text of the chunk
    """
    rel_path = file_path.relative_to(repo_root).as_posix()
    try:
        source = file_path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return []

    if not source.strip():
        return []

    chunks: list[dict[str, Any]] = []
    try:
        tree = ast.parse(source)
        lines = source.splitlines(keepends=True)
        top_level = [
            node for node in ast.iter_child_nodes(tree)
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))
        ]
        for node in top_level:
            start = node.lineno - 1          # 0-indexed
            end = node.end_lineno            # exclusive (end_lineno is inclusive)
            snippet = "".join(lines[start:end]).rstrip()
            if snippet:
                chunks.append(
                    {"file": rel_path, "start_line": node.lineno, "snippet": snippet}
                )
    except SyntaxError:
        pass

    # If we couldn't extract any function/class chunks, use the whole file
    if not chunks:
        chunks.append({"file": rel_path, "start_line": 1, "snippet": source.rstrip()})

    return chunks


class RepoIndexer:
    COLLECTION_NAME = "repo_index"

    def __init__(self, repo_root: str) -> None:
        self.repo_root = Path(repo_root).resolve()
        persist_dir = str(self.repo_root / ".chroma")
        self._client = chromadb.PersistentClient(path=persist_dir)
        self._ef = embedding_functions.DefaultEmbeddingFunction()
        self._collection = self._client.get_or_create_collection(
            name=self.COLLECTION_NAME,
            embedding_function=self._ef,
            metadata={"hnsw:space": "cosine"},
        )
        self._build_index()

    # ------------------------------------------------------------------
    # Index construction
    # ------------------------------------------------------------------

    def reindex(self) -> int:
        try:
            self._client.delete_collection(name=self.COLLECTION_NAME)
        except Exception:
            pass  # Collection may not exist yet
        self._collection = self._client.get_or_create_collection(
            name=self.COLLECTION_NAME,
            embedding_function=self._ef,
            metadata={"hnsw:space": "cosine"},
        )
        self._build_index(force=True)
        return self._collection.count()

    def _build_index(self, force: bool = False) -> None:
        """Index the repo; skips work if the collection already has documents (unless force=True)."""
        if not force and self._collection.count() > 0:
            logger.info(
                "RepoIndexer: collection already has %d chunks — skipping re-index.",
                self._collection.count(),
            )
            return

        logger.info("RepoIndexer: indexing %s …", self.repo_root)
        chunks: list[dict[str, Any]] = []
        for py_file in _iter_python_files(self.repo_root):
            chunks.extend(_chunk_file(py_file, self.repo_root))

        if not chunks:
            logger.warning("RepoIndexer: no Python source found under %s", self.repo_root)
            return

        # ChromaDB requires string IDs; derive a stable one from file+line
        ids = [
            hashlib.md5(f"{c['file']}:{c['start_line']}".encode()).hexdigest()
            for c in chunks
        ]
        documents = [c["snippet"] for c in chunks]
        metadatas = [{"file": c["file"], "start_line": c["start_line"]} for c in chunks]

        # Upsert in batches of 500 to avoid request-size limits
        batch_size = 500
        for i in range(0, len(chunks), batch_size):
            self._collection.upsert(
                ids=ids[i : i + batch_size],
                documents=documents[i : i + batch_size],
                metadatas=metadatas[i : i + batch_size],
            )

        logger.info("RepoIndexer: indexed %d chunks.", len(chunks))

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def query(self, text: str, n_results: int = 5) -> list[dict[str, Any]]:
        """
        Return the *n_results* most semantically similar code chunks.

        Each result dict contains:
            file       – repo-relative file path
            start_line – line number where the chunk starts
            snippet    – the source text
            distance   – cosine distance (lower = more similar)
        """
        if not text or not text.strip():
            return []

        count = self._collection.count()
        if count == 0:
            return []

        safe_n = min(n_results, count)
        results = self._collection.query(
            query_texts=[text],
            n_results=safe_n,
            include=["documents", "metadatas", "distances"],
        )

        hits: list[dict[str, Any]] = []
        docs = results.get("documents", [[]])[0]
        metas = results.get("metadatas", [[]])[0]
        dists = results.get("distances", [[]])[0]

        for doc, meta, dist in zip(docs, metas, dists):
            hits.append(
                {
                    "file": meta.get("file", ""),
                    "start_line": meta.get("start_line", 0),
                    "snippet": doc,
                    "distance": round(dist, 4),
                }
            )
        return hits
