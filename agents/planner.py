from __future__ import annotations

import logging
from typing import Any, TYPE_CHECKING

from config import settings
from schemas.schemas import StructuredPlan
from langchain_core.messages import SystemMessage, HumanMessage
from agents.llm_factory import build_llm

if TYPE_CHECKING:
    from tools.indexing import RepoIndexer

logger = logging.getLogger(__name__)




def _format_hits(hits: list[dict[str, Any]]) -> str:
    """Render index hits as a readable string for the LLM prompt."""
    if not hits:
        return "(no relevant code found)"
    parts: list[str] = []
    for i, hit in enumerate(hits, 1):
        parts.append(
            f"[{i}] {hit['file']} (line {hit['start_line']}, distance={hit['distance']}):\n"
            f"```python\n{hit['snippet']}\n```"
        )
    return "\n\n".join(parts)


class PlannerAgent:
    def __init__(self, indexer: "RepoIndexer | None" = None) -> None:
        self.llm = build_llm(structured_output=StructuredPlan)
        self.indexer = indexer

    def plan(self, bug_description: str) -> dict[str, Any]:
        # Semantic search: retrieve the most relevant code chunks
        if self.indexer is not None:
            try:
                hits = self.indexer.query(
                    bug_description, n_results=settings.chroma_n_results
                )
            except Exception as exc:
                logger.warning("RepoIndexer.query failed: %s — falling back to empty hits.", exc)
                hits = []
        else:
            hits = []

        index_context = _format_hits(hits)

        sys = SystemMessage(
            content=(
                "You are an expert software engineer and planner. Given a bug description and code context, "
                "you MUST return a single JSON object.\n"
                "CRITICAL CONSTRAINTS:\n"
                "1. 'files_to_modify' MUST be a list of UNIQUE strings (file paths). Do NOT repeat the same file.\n"
                "2. 'patches': generate ONE patch per function to fix. Do NOT create multiple patches for the same function.\n"
                "3. 'patches[].new_code' MUST contain ONLY the function body statements — "
                "NOT the 'def' line itself. Example: if fixing 'def add(a,b): pass', "
                "set new_code to 'return a + b' (just the body), NOT 'def add(a,b): return a + b'.\n"
                "4. 'tests_to_add' objects MUST contain 'file_path', 'test_name', and 'content'.\n"
                "5. Do NOT include any text before or after the JSON. Return JUST the JSON object.\n"
                "6. Use ONLY standard JSON booleans (true/false) and null. Do NOT use Python True/False/None."
            )
        )
        human = HumanMessage(
            content=(
                f"Bug: {bug_description}\n\n"
                f"Relevant code (semantic search results):\n{index_context}"
            )
        )
        response = self.llm.invoke([sys, human])
        if response is not None:
            return {"ok": True, "plan": response.model_dump()}
        else:
            raise ValueError("No plan found")
