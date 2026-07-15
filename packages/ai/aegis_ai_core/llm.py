"""
LLM providers used for RAG answer generation.

`OllamaLLMProvider` talks to a local Ollama server (per the tech stack —
Llama 3, no external API key or per-token cost). `FakeLLMProvider` is a
deterministic stand-in for tests: this environment has no running Ollama
server, so tests never depend on that network call — the same pattern as
the other providers in this package.
"""
from typing import Protocol

from langsmith import traceable


class LLMProvider(Protocol):
    def generate(self, prompt: str) -> str: ...


class OllamaLLMProvider:
    """Production LLM provider — plain HTTP against a local Ollama server's
    /api/generate endpoint. No extra client library: Ollama's HTTP API is
    small and stable enough that a thin httpx wrapper is more transparent
    (and one fewer dependency to version-pin) than a full SDK."""

    def __init__(self, base_url: str, model: str, timeout_seconds: float = 60.0):
        self._base_url = base_url.rstrip("/")
        self._model = model
        self._timeout = timeout_seconds

    @traceable(run_type="llm", name="ollama_generate")
    def generate(self, prompt: str) -> str:
        import httpx

        response = httpx.post(
            f"{self._base_url}/api/generate",
            json={"model": self._model, "prompt": prompt, "stream": False},
            timeout=self._timeout,
        )
        response.raise_for_status()
        return response.json()["response"]


class FakeLLMProvider:
    """
    Deterministic stand-in for tests. Doesn't call any model — just
    produces a templated answer referencing the prompt's context section,
    so RAG plumbing (retrieval → prompt assembly → "generation" → citation
    storage) can be tested end-to-end without a running Ollama server.
    """

    def generate(self, prompt: str) -> str:
        return (
            "Based on the retrieved context, here is a summary answer. "
            "(This is a deterministic test response — no real LLM was called.)"
        )
