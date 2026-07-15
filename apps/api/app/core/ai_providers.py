"""
Factory accessors for the shared AI providers (embeddings, vector store,
LLM), wiring `app.core.config.Settings` into the environment-agnostic
`aegis_ai_core` package.

Kept here (rather than instantiating providers inline wherever needed) so
there's exactly one place that decides "production uses HuggingFace +
Pinecone + Ollama, dev/test can substitute fakes" — routes, services, and
Celery tasks all go through these functions.
"""
from aegis_ai_core.embeddings import EmbeddingProvider, HuggingFaceEmbeddingProvider
from aegis_ai_core.llm import LLMProvider, OllamaLLMProvider
from aegis_ai_core.vector_store import VectorStoreBackend, get_vector_store as _get_vector_store

from app.core.config import get_settings

settings = get_settings()

_embedding_singleton: EmbeddingProvider | None = None
_llm_singleton: LLMProvider | None = None


def get_embedding_provider() -> EmbeddingProvider:
    """
    FastAPI dependency / plain accessor for the configured embedding
    provider. Lazily constructed (loading the model is expensive) and
    cached as a process-wide singleton. Overridden in tests via
    `app.dependency_overrides` with `FakeEmbeddingProvider`.
    """
    global _embedding_singleton
    if _embedding_singleton is None:
        _embedding_singleton = HuggingFaceEmbeddingProvider(settings.EMBEDDING_MODEL_NAME)
    return _embedding_singleton


def get_vector_store() -> VectorStoreBackend:
    """FastAPI dependency / plain accessor for the configured vector store
    (FAISS in dev, Pinecone in production, selected by ENVIRONMENT)."""
    return _get_vector_store(
        environment=settings.ENVIRONMENT,
        faiss_index_dir=settings.FAISS_INDEX_DIR,
        pinecone_api_key=settings.PINECONE_API_KEY,
        pinecone_index_name=settings.PINECONE_INDEX_NAME,
    )


def get_llm_provider() -> LLMProvider:
    """FastAPI dependency / plain accessor for the configured LLM provider."""
    global _llm_singleton
    if _llm_singleton is None:
        _llm_singleton = OllamaLLMProvider(settings.OLLAMA_BASE_URL, settings.OLLAMA_MODEL)
    return _llm_singleton
