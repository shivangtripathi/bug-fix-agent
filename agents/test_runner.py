from __future__ import annotations

import logging
import re
import subprocess
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


class TestRunnerAgent:
    def __init__(self, repo_root: str) -> None:
        self.repo_root = repo_root
        self.tests_dir = Path(repo_root) / "tests"

    def run(self) -> dict[str, Any]:
        if not self.tests_dir.exists():
            return {
                "ok": False,
                "returncode": -1,
                "summary": "No tests/ directory found",
                "output": "",
            }

        completed = subprocess.run(
            ["python", "-m", "pytest", str(self.tests_dir), "--tb=short", "-q"],
            cwd=self.repo_root,
            text=True,
            capture_output=True,
        )

        full_output = (completed.stdout + completed.stderr).strip()
        summary = self._parse_summary(full_output)

        logger.info("pytest finished (rc=%d): %s", completed.returncode, summary)

        return {
            "ok": completed.returncode == 0,
            "returncode": completed.returncode,
            "summary": summary,
            "output": full_output,
        }

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _parse_summary(output: str) -> str:
        # pytest short summary line pattern
        match = re.search(
            r"(\d+ (?:passed|failed|error)[^\n]*)",
            output,
            re.IGNORECASE,
        )
        if match:
            # strip timing suffix " in 0.12s"
            return re.sub(r"\s+in\s+[\d.]+s$", "", match.group(1)).strip()

        # fallback: last non-empty line
        lines = [l.strip() for l in output.splitlines() if l.strip()]
        return lines[-1] if lines else "no output"
