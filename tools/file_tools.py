from __future__ import annotations

from pathlib import Path
from typing import Any


def _resolve(file_path: str, repo_root: str) -> Path:
    """Return an absolute path, anchored to repo_root when file_path is relative."""
    p = Path(file_path)
    if repo_root and not p.is_absolute():
        return Path(repo_root) / p
    return p


def read_file(file_path: str, repo_root: str = "") -> dict[str, Any]:
    path = _resolve(file_path, repo_root)
    if not path.exists():
        return {"ok": False, "error": "file_not_found", "file_path": file_path}
    content = path.read_text(encoding="utf-8")
    return {"ok": True, "file_path": file_path, "content": content}


def write_file(file_path: str, content: str, repo_root: str = "") -> dict[str, Any]:
    path = _resolve(file_path, repo_root)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return {
        "ok": True,
        "file_path": file_path,
        "bytes_written": len(content.encode("utf-8")),
    }
