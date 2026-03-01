from __future__ import annotations

import os
from dataclasses import dataclass
import dotenv

dotenv.load_dotenv()


@dataclass(slots=True)
class Settings:
    llm_provider: str = os.getenv("LLM_PROVIDER", "gemini").lower()
    gemini_model: str = os.getenv("GEMINI_MODEL", "gemini-3-flash")
    ollama_model: str = os.getenv("OLLAMA_MODEL", "gemma:2b")
    ollama_base_url: str = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
    langsmith_tracing: bool = os.getenv("LANGSMITH_TRACING", "false").lower() == "true"
    langsmith_project: str = os.getenv("LANGSMITH_PROJECT", "bugfix-agent")
    max_context_chars: int = int(os.getenv("MAX_CONTEXT_CHARS", "32000"))
    chroma_n_results: int = int(os.getenv("CHROMA_N_RESULTS", "5"))
    # ~8 k tokens @ 4 chars/token — trigger LLM compression above this
    compression_threshold_chars: int = int(os.getenv("COMPRESSION_THRESHOLD_CHARS", "32000"))


settings = Settings()
