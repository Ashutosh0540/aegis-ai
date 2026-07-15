"""
LangSmith tracing bridge.

LangChain/LangGraph auto-detect tracing configuration from environment
variables (`LANGCHAIN_TRACING_V2`, `LANGCHAIN_API_KEY`, etc.) rather than
an explicit API. This module's only job is to copy `Settings.LANGCHAIN_*`
into `os.environ` once at process startup, so tracing is configured the
same way (via our normal `.env`) as everything else, without every call
site needing to know about LangSmith specifically.

Genuinely a no-op with zero network calls when `LANGCHAIN_TRACING_V2` is
false (the default) — this sandbox has no LangSmith API access, so tests
and local dev run with tracing off unless explicitly configured.
"""
import os

from app.core.config import get_settings


def configure_langsmith() -> None:
    settings = get_settings()

    os.environ["LANGCHAIN_TRACING_V2"] = "true" if settings.LANGCHAIN_TRACING_V2 else "false"
    os.environ["LANGCHAIN_PROJECT"] = settings.LANGCHAIN_PROJECT
    os.environ["LANGCHAIN_ENDPOINT"] = settings.LANGCHAIN_ENDPOINT
    if settings.LANGCHAIN_API_KEY:
        os.environ["LANGCHAIN_API_KEY"] = settings.LANGCHAIN_API_KEY
