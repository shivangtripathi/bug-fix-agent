from __future__ import annotations

from config import settings


def build_llm(structured_output=None):
    """Build and return the configured LLM, optionally wrapped with structured output."""
    if settings.llm_provider == "ollama":
        from langchain_community.chat_models import ChatOllama

        llm = ChatOllama(model=settings.ollama_model, base_url=settings.ollama_base_url)

    elif settings.llm_provider == "gemini":
        from langchain_google_genai import ChatGoogleGenerativeAI

        llm = ChatGoogleGenerativeAI(model=settings.gemini_model, temperature=0)

    else:
        raise ValueError(f"Unsupported LLM provider: {settings.llm_provider}")

    if structured_output is not None:
        return llm.with_structured_output(structured_output)
    return llm
