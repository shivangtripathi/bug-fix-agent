from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from langchain_core.messages import SystemMessage, HumanMessage

from agents.llm_factory import build_llm
from schemas.schemas import GeneratedTests
from tools.file_tools import read_file

logger = logging.getLogger(__name__)

_SYSTEM_PROMPT = """\
You are an expert Python test engineer. Given a bug fix plan and the patched source code,
generate comprehensive pytest test cases.

Rules:
1. Use pytest conventions — plain functions starting with `test_`, no unittest.TestCase.
2. Each test function must have a clear docstring explaining what it tests.
3. Test both the happy path AND edge cases (e.g. zero inputs, negatives, type errors).
4. Import only from the standard library and the module under test.
5. Return a list of test files. Each file has:
   - 'filename': just the base name, e.g. "test_calculator.py" (no directory prefix)
   - 'content': the complete file content as a string
6. Do NOT include any explanation outside the JSON.
"""


class TestGeneratorAgent:
    def __init__(self, repo_root: str) -> None:
        self.repo_root = repo_root
        self.tests_dir = Path(repo_root) / "tests"
        self.llm = build_llm(structured_output=GeneratedTests)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def generate(self, plan: dict[str, Any], patch_results: dict[str, Any]) -> dict[str, Any]:
        self.tests_dir.mkdir(parents=True, exist_ok=True)
        self._ensure_init()

        source_context = self._build_source_context(plan, patch_results)
        plan_context = self._build_plan_context(plan)

        try:
            response: GeneratedTests = self.llm.invoke([
                SystemMessage(content=_SYSTEM_PROMPT),
                HumanMessage(content=(
                    f"Fix plan:\n{plan_context}\n\n"
                    f"Patched source files:\n{source_context}"
                )),
            ])
        except Exception as exc:
            logger.error("TestGeneratorAgent LLM call failed: %s", exc)
            return {"ok": False, "tests_dir": str(self.tests_dir), "files_written": [], "errors": [str(exc)]}

        files_written: list[str] = []
        errors: list[str] = []

        for test_file in response.test_files:
            dest = self.tests_dir / test_file.filename
            try:
                dest.write_text(test_file.content, encoding="utf-8")
                files_written.append(str(dest))
                logger.info("Wrote test file: %s", dest)
            except Exception as exc:
                errors.append(f"{dest}: {exc}")
                logger.error("Failed to write %s: %s", dest, exc)

        return {
            "ok": len(errors) == 0,
            "tests_dir": str(self.tests_dir),
            "files_written": files_written,
            "errors": errors,
        }

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _ensure_init(self) -> None:
        """Create __init__.py in tests/ if absent so pytest discovers tests."""
        init = self.tests_dir / "__init__.py"
        if not init.exists():
            init.write_text("")

    def _build_plan_context(self, plan: dict[str, Any]) -> str:
        lines = [
            f"Bug summary: {plan.get('bug_summary', 'N/A')}",
            f"Root cause:  {plan.get('root_cause', 'N/A')}",
            f"Files modified: {', '.join(plan.get('files_to_modify', []))}",
        ]
        for patch in plan.get("patches", []):
            fn = patch.get("function_name", "?")
            rationale = patch.get("rationale", "")
            lines.append(f"  - patched function '{fn}': {rationale}")
        return "\n".join(lines)

    def _build_source_context(self, plan: dict[str, Any], patch_results: dict[str, Any]) -> str:
        """Read the patched source files and return them as a formatted string."""
        parts: list[str] = []

        for file_path in plan.get("files_to_modify", []):
            result = read_file(file_path, self.repo_root)
            content = result.get("content", "")
            if content:
                parts.append(f"### {file_path}\n```python\n{content}\n```")
            else:
                logger.warning("Could not read patched file: %s", file_path)

        return "\n\n".join(parts) if parts else "(source files unavailable)"
