from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from tools.ast_editor import edit_file
from tools.bash_tool import bash
from tools.file_tools import read_file, write_file

logger = logging.getLogger(__name__)


class ExecutorAgent:
    """
    Applies code patches from a plan.

    Key design decisions:
    - Patches on the SAME file are applied sequentially so each patch reads
      the output of the previous one (not the original). This prevents N
      independent patches from all clobbering each other.
    - Test generation and running are handled by separate agent nodes.
    """

    def __init__(self, repo_root: str = "") -> None:
        self.repo_root = repo_root

    def execute(self, plan: dict[str, Any]) -> dict[str, Any]:
        results: dict[str, Any] = {
            "reads": [],
            "patches": [],
            "writes": [],
            "bash": [],
        }

        # Read source files for context (informational only)
        for file_path in plan.get("files_to_modify", []):
            results["reads"].append(read_file(file_path, self.repo_root))

        current_content: dict[str, str] = {}

        for patch in plan.get("patches", []):
            file_path: str = patch.get("file_path", "")
            if not file_path:
                continue

            resolved = str(Path(self.repo_root) / file_path) if self.repo_root and not Path(file_path).is_absolute() else file_path

            if resolved in current_content:
                Path(resolved).write_text(current_content[resolved], encoding="utf-8")

            transform = {
                "type": "rewrite_function",
                "function_name": patch.get("function_name"),
                "new_body": patch.get("new_code", "pass"),
            }
            patched = edit_file(file_path, transform, self.repo_root)
            results["patches"].append(patched)

            if patched.get("ok"):
                updated = patched["updated_content"]
                current_content[resolved] = updated
                write_result = write_file(file_path, updated, self.repo_root)
                results["writes"].append(write_result)
                logger.info("Patched %s (fn=%s)", file_path, patch.get("function_name"))
            else:
                logger.warning(
                    "Patch failed for %s fn=%s: %s",
                    file_path,
                    patch.get("function_name"),
                    patched.get("error"),
                )

        for command in plan.get("bash_commands", []):
            results["bash"].append(bash(command))

        return {"ok": True, "results": results}
