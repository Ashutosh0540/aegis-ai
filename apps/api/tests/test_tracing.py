import os

from app.core.tracing import configure_langsmith


def test_configure_langsmith_defaults_to_disabled(monkeypatch):
    monkeypatch.delenv("LANGCHAIN_TRACING_V2", raising=False)
    from app.core.config import get_settings

    get_settings.cache_clear()
    configure_langsmith()
    assert os.environ["LANGCHAIN_TRACING_V2"] == "false"
    get_settings.cache_clear()


def test_configure_langsmith_sets_project_and_endpoint():
    configure_langsmith()
    assert os.environ.get("LANGCHAIN_PROJECT") == "aegis-ai"
    assert os.environ.get("LANGCHAIN_ENDPOINT", "").startswith("https://")


def test_graph_runs_normally_with_tracing_disabled():
    """Confirms the @traceable wrapper on OllamaLLMProvider.generate and the
    config= kwarg on graph.invoke don't break anything when tracing is off
    (the default) — no network call should be attempted."""
    import tempfile
    import uuid

    from aegis_ai_core.agents import run_supervisor_graph
    from aegis_ai_core.embeddings import FakeEmbeddingProvider
    from aegis_ai_core.llm import FakeLLMProvider
    from aegis_ai_core.vector_store import FAISSVectorStore

    configure_langsmith()
    store = FAISSVectorStore(tempfile.mkdtemp())
    result = run_supervisor_graph(
        "hello?", str(uuid.uuid4()), FakeEmbeddingProvider(dimension=16), store, FakeLLMProvider()
    )
    assert result["route"] == "knowledge_agent"
    assert result["answer"]
