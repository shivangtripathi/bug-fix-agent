from __future__ import annotations

from typing import Any, Iterator

from langsmith import traceable

from config import settings
from agents.planner import PlannerAgent
from agents.executor import ExecutorAgent
from agents.test_generator import TestGeneratorAgent
from agents.test_runner import TestRunnerAgent
from agents.conversation_agent import ConversationAgent
from tools.indexing import RepoIndexer


class Orchestrator:
    def __init__(self, repo_root: str) -> None:
        self.repo_root = repo_root
        self.indexer = RepoIndexer(repo_root)
        self.conversation_agent = ConversationAgent(indexer=self.indexer)
        self.planner = PlannerAgent(indexer=self.indexer)
        self.executor = ExecutorAgent(repo_root)
        self.test_generator = TestGeneratorAgent(repo_root)
        self.test_runner = TestRunnerAgent(repo_root)
        self._pending_plan: dict[str, Any] | None = None

    # ------------------------------------------------------------------
    # Non-streaming conversation turn (used with thinking loader)
    # ------------------------------------------------------------------

    @traceable(name="chat_turn")
    def chat_turn(self, user_message: str) -> dict[str, Any]:
        self.conversation_agent.compress_history()
        self._pending_plan = None
        reply, ready = self.conversation_agent.respond(user_message)
        if ready:
            bug_description = self.conversation_agent.get_bug_description()
            plan_result = self.planner.plan(bug_description)
            self._pending_plan = plan_result.get("plan")
        return {"reply": reply, "plan": self._pending_plan}

    # ------------------------------------------------------------------
    # Granular execute helpers (each can be called separately with a
    # user-permission gate in between)
    # ------------------------------------------------------------------

    @traceable(name="apply_patches")
    def apply_patches(self, plan: dict[str, Any]) -> dict[str, Any]:
        """Apply code patches from plan. Returns executor result dict."""
        return self.executor.execute(plan)

    @traceable(name="generate_tests")
    def generate_tests(self, plan: dict[str, Any], patch_result: dict[str, Any]) -> dict[str, Any]:
        """Generate test files. Returns test_generator result dict."""
        return self.test_generator.generate(plan, patch_result)

    @traceable(name="run_tests")
    def run_tests(self) -> dict[str, Any]:
        """Run pytest on the repo's tests/ directory."""
        return self.test_runner.run()

    def record_fix_and_reindex(self, plan: dict[str, Any]) -> None:
        """Record the applied fix in conversation context and re-index."""
        if plan and plan.get("bug_summary"):
            self.conversation_agent.record_fix(plan["bug_summary"])
            self.indexer.reindex()