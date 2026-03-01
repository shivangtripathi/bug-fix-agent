from __future__ import annotations

import logging
from typing import Any, Iterator, TYPE_CHECKING

from langchain_core.messages import SystemMessage, HumanMessage, AIMessage

from agents.llm_factory import build_llm
from agents.guardrails import Guardrails, REFUSAL_MESSAGE
from config import settings
import re
from pathlib import Path

if TYPE_CHECKING:
    from tools.indexing import RepoIndexer

logger = logging.getLogger(__name__)

_COMPRESS_PROMPT = (
    "You are a helpful assistant that summarises software-debugging conversations.\n"
    "Below is a fragment of a conversation between a developer and a debugging assistant.\n"
    "Write a dense, factual summary (max 400 words) that preserves:\n"
    "- The bug(s) described and their root causes\n"
    "- Any clarifications the developer provided\n"
    "- Proposed or applied fixes\n"
    "- Any unresolved questions\n"
    "Do NOT add opinions or padding.  Output only the summary text.\n\n"
    "CONVERSATION FRAGMENT:\n{fragment}"
)

READY_SIGNAL = "[READY_TO_FIX]"

SYSTEM_PROMPT = """\
You are an expert software engineering assistant that helps developers debug and fix code.

## Conversation rules
1. **Understand first.** Ask ONE targeted clarifying question at a time if you need more
   information (e.g. how to reproduce, which function is affected, expected vs actual output).

2. **Discuss findings.** Once you have enough context, explain your understanding of the
   root cause. Invite the developer to confirm or correct you.

3. **Propose a fix.** When you are confident, briefly describe what you plan to change,
   then end your message with the exact token: {signal}
   Only emit {signal} when you are truly confident AND the user has not asked you to
   keep discussing.

4. **Post-fix follow-ups.** After a fix is applied the conversation continues.
   Treat new issues as fresh bugs and restart the cycle.

5. **Context.** You receive:
   - Full conversation history
   - Summary of any previously applied fixes
   - Relevant code snippets from semantic search of the repo

Tone: conversational, concise, helpful. No preamble.
""".format(signal=READY_SIGNAL)


def _format_hits(hits: list[dict[str, Any]]) -> str:
    if not hits:
        return "(no relevant code found)"
    parts: list[str] = []
    for i, hit in enumerate(hits, 1):
        parts.append(
            f"[{i}] {hit['file']} (line {hit['start_line']}, distance={hit['distance']}):\n"
            f"```python\n{hit['snippet']}\n```"
        )
    return "\n\n".join(parts)


class ConversationAgent:
    """
    Manages the conversational phase of bug investigation.

    Keeps a running list of LangChain messages and queries the LLM on every
    user turn.  Returns the assistant's plain-text reply and a boolean flag
    indicating whether it has signalled READY_TO_FIX.
    """

    def __init__(self, indexer: "RepoIndexer | None" = None) -> None:
        self.llm = build_llm()          # plain LLM — free-form text output
        self.indexer = indexer
        self.guardrails = Guardrails()
        self.messages: list = [SystemMessage(content=SYSTEM_PROMPT)]
        self.fix_history: list[str] = []   # summaries of applied fixes

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def respond(self, user_message: str) -> tuple[str, bool]:
        """
        Process one user turn.

        Returns
        -------
        reply : str
            The assistant's plain-text response (READY_SIGNAL stripped).
        ready : bool
            True if the agent has decided it's time to invoke the planner.
        """
        # ── Guardrail check ────────────────────────────────────────────────
        if not self.guardrails.is_allowed(user_message):
            logger.info("Guardrail blocked message: %r", user_message[:80])
            self.messages.append(HumanMessage(content=user_message))
            self.messages.append(AIMessage(content=REFUSAL_MESSAGE))
            return REFUSAL_MESSAGE, False

        # Build context: semantic search based on latest user message
        index_context = self._query_index(user_message)
        file_context = self._get_mentioned_files_content(user_message)
        fix_context = self._fix_summary()

        # Inject ephemeral context as a system note before the user message
        context_note = ""
        if index_context or fix_context or file_context:
            parts = []
            if fix_context:
                parts.append(f"Previously applied fixes:\n{fix_context}")
            if file_context:
                parts.append(f"Contents of explicitly mentioned files:\n{file_context}")
            if index_context:
                parts.append(f"Relevant code from repo:\n{index_context}")
            context_note = "\n\n---\n" + "\n\n".join(parts) + "\n---"

        # Append user turn (with context note appended to it for the LLM)
        full_user_content = user_message + context_note
        self.messages.append(HumanMessage(content=full_user_content))

        # Call LLM
        response = self.llm.invoke(self.messages)
        raw_reply: str = response.content if hasattr(response, "content") else str(response)

        # Detect readiness signal
        ready = READY_SIGNAL in raw_reply
        clean_reply = raw_reply.replace(READY_SIGNAL, "").strip()

        # Store AI message (without the signal, for cleaner history)
        self.messages.append(AIMessage(content=clean_reply))

        return clean_reply, ready

    def record_fix(self, bug_summary: str) -> None:
        self.fix_history.append(bug_summary)

    def get_bug_description(self) -> str:
        human_msgs = [
            m.content.split("\n\n---")[0]   # strip the context note we injected
            for m in self.messages
            if isinstance(m, HumanMessage)
        ]
        return "\n".join(human_msgs[-4:])   # last 4 human turns

    def compress_history(self) -> None:
        # Count raw chars across all messages
        total_chars = sum(len(m.content) for m in self.messages)
        if total_chars <= settings.compression_threshold_chars:
            return  # nothing to do

        # Separate system prompt from the rest
        if self.messages and isinstance(self.messages[0], SystemMessage):
            system_msg = self.messages[0]
            history = self.messages[1:]
        else:
            system_msg = None
            history = list(self.messages)

        # Keep the last 4 messages (≈ 2 human+AI turns) intact
        keep_recent = 4
        to_compress = history[:-keep_recent] if len(history) > keep_recent else []
        recent = history[-keep_recent:] if len(history) >= keep_recent else history

        if not to_compress:
            return  # not enough history to compress

        # Build the fragment text for the LLM to summarise
        fragment_parts: list[str] = []
        for msg in to_compress:
            role = "User" if isinstance(msg, HumanMessage) else "Assistant"
            # Strip injected context notes before summarising
            content = msg.content.split("\n\n---")[0].strip()
            fragment_parts.append(f"{role}: {content}")
        fragment = "\n".join(fragment_parts)

        prompt = _COMPRESS_PROMPT.format(fragment=fragment)
        try:
            response = self.llm.invoke([HumanMessage(content=prompt)])
            summary_text: str = (
                response.content if hasattr(response, "content") else str(response)
            ).strip()
        except Exception as exc:
            logger.warning("compress_history LLM call failed: %s", exc)
            return

        logger.info(
            "Compressed %d messages into a summary (%d chars -> %d chars).",
            len(to_compress),
            sum(len(m.content) for m in to_compress),
            len(summary_text),
        )

        summary_msg = SystemMessage(
            content=f"[Compressed conversation summary]\n{summary_text}"
        )

        # Reconstruct: original system prompt → summary → recent messages
        self.messages = (
            ([system_msg] if system_msg else []) + [summary_msg] + recent
        )

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _query_index(self, query: str) -> str:
        if self.indexer is None:
            return ""
        try:
            hits = self.indexer.query(query, n_results=settings.chroma_n_results)
            return _format_hits(hits)
        except Exception as exc:
            logger.warning("RepoIndexer.query failed: %s", exc)
            return ""

    def _get_mentioned_files_content(self, text: str) -> str:
        """Finds file names mentioned in text and returns their content."""
        if self.indexer is None:
            return ""
        
        # Look for things that look like filenames (e.g. foo.py, src/calc.py)
        mentioned_files = set(re.findall(r'[\w/.-]+\.\w+', text))
        if not mentioned_files:
            return ""

        repo_root = Path(self.indexer.repo_root)
        parts = []
        for filename in mentioned_files:
            try:
                # Search for the file in the repo root
                found_paths = list(repo_root.rglob(Path(filename).name))
                for path in found_paths:
                    # Ignore common ignore directories
                    if any(ignored in path.parts for ignored in ['.git', '__pycache__', '.venv', 'venv']):
                        continue
                    content = path.read_text(encoding="utf-8")
                    rel_path = path.relative_to(repo_root).as_posix()
                    parts.append(f"--- Full content of {rel_path} ---\n```python\n{content}\n```")
            except Exception as exc:
                logger.warning(f"Failed to read mentioned file {filename}: {exc}")

        return "\n\n".join(parts)

    def _fix_summary(self) -> str:
        if not self.fix_history:
            return ""
        return "\n".join(f"- {s}" for s in self.fix_history)
