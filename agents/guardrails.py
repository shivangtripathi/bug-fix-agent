from __future__ import annotations

import logging
from agents.llm_factory import build_llm
from langchain_core.messages import SystemMessage, HumanMessage

logger = logging.getLogger(__name__)

# Topics that are clearly in-scope
_SCOPE_DESCRIPTION = (
    "software bugs, code errors, debugging, crash reports, test failures, "
    "unexpected behaviour in code, stack traces, performance regressions, "
    "security vulnerabilities in code, and asking for code fixes or patches,"
    "request to check/inspect code,"
    "Requests that imply troubleshooting or investigation of existing code, even if a bug is not explicitly stated"
)

_CLASSIFIER_SYSTEM = f"""\
You are a strict intent classifier for a bug-fixing assistant.

Your ONLY job is to decide whether the user's message is related to software debugging and bug fixing.

In-scope topics: {_SCOPE_DESCRIPTION}.

Out-of-scope topics: general knowledge questions, creative writing, math homework, \
opinions, weather, jokes, coding tutorials unrelated to a specific bug, feature requests, \
general programming advice with no bug to fix, and anything else not directly related to \
debugging or fixing a concrete software issue.

Respond with EXACTLY one word — either:
  ALLOWED   (if the message is bug/debugging related)
  BLOCKED   (if the message is off-topic)

No explanation. No punctuation. Just the single word.
"""

REFUSAL_MESSAGE = (
    "I'm a specialised bug-fixing assistant and can only help with software bugs, "
    "errors, crashes, test failures, or code issues. "
    "Please describe a bug or paste an error message and I'll dig in."
)


class Guardrails:
    # Short conversational replies that are always in-context follow-ups, never off-topic.
    # The LLM classifier should never even see these — they have no standalone meaning.
    _CONVERSATIONAL_REPLIES: frozenset[str] = frozenset({
        "y", "n", "yes", "no", "ok", "okay", "sure", "agree", "agreed",
        "correct", "yep", "yup", "nope", "nah", "right", "exactly",
        "go ahead", "proceed", "fix it", "apply", "looks good",
        "sounds good", "confirm", "confirmed", "that's right", "yeah",
    })

    # Messages this short are always replies within an ongoing conversation
    _SHORT_MSG_THRESHOLD = 25

    def __init__(self) -> None:
        self._llm = build_llm()

    def is_allowed(self, user_message: str) -> bool:
        """Return True if the message is on-topic (bug/debugging related)."""
        normalized = user_message.strip().lower()

        if normalized in self._CONVERSATIONAL_REPLIES or len(normalized) <= self._SHORT_MSG_THRESHOLD:
            logger.debug("Guardrail fast-pass (conversational reply): %r", user_message[:60])
            return True

        try:
            response = self._llm.invoke([
                SystemMessage(content=_CLASSIFIER_SYSTEM),
                HumanMessage(content=user_message),
            ])
            verdict = (response.content if hasattr(response, "content") else str(response)).strip().upper()
            logger.debug("Guardrail verdict for %r: %s", user_message[:60], verdict)
            return verdict != "BLOCKED"
        except Exception as exc:
            logger.warning("Guardrail check failed (%s) — defaulting to ALLOWED.", exc)
            return True  # fail-open: never block when classifier is unavailable
