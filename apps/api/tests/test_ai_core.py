import tempfile
import uuid

from aegis_ai_core.embeddings import FakeEmbeddingProvider
from aegis_ai_core.llm import FakeLLMProvider
from aegis_ai_core.prompts import build_rag_prompt, format_context, format_history
from aegis_ai_core.vector_store import FAISSVectorStore


def test_fake_embedding_provider_is_deterministic():
    provider = FakeEmbeddingProvider(dimension=32)
    v1 = provider.embed_text("hello world")
    v2 = provider.embed_text("hello world")
    assert v1 == v2
    assert len(v1) == 32


def test_fake_embedding_provider_different_text_different_vector():
    provider = FakeEmbeddingProvider(dimension=32)
    v1 = provider.embed_text("cats and dogs")
    v2 = provider.embed_text("quantum mechanics")
    assert v1 != v2


def test_faiss_vector_store_upsert_and_query_ranks_by_similarity():
    store = FAISSVectorStore(tempfile.mkdtemp())
    provider = FakeEmbeddingProvider(dimension=32)
    org_id = str(uuid.uuid4())
    relevant_id, irrelevant_id = str(uuid.uuid4()), str(uuid.uuid4())

    store.upsert(
        org_id, relevant_id, provider.embed_text("employee vacation policy"),
        {"document_id": "docA", "content": "employee vacation policy"},
    )
    store.upsert(
        org_id, irrelevant_id, provider.embed_text("server room temperature specs"),
        {"document_id": "docB", "content": "server room temperature specs"},
    )

    results = store.query(org_id, provider.embed_text("vacation policy"), top_k=2)
    assert results[0].chunk_id == relevant_id


def test_faiss_vector_store_filters_by_document_id():
    store = FAISSVectorStore(tempfile.mkdtemp())
    provider = FakeEmbeddingProvider(dimension=32)
    org_id = str(uuid.uuid4())
    chunk_a, chunk_b = str(uuid.uuid4()), str(uuid.uuid4())

    store.upsert(org_id, chunk_a, provider.embed_text("policy text"), {"document_id": "docA"})
    store.upsert(org_id, chunk_b, provider.embed_text("policy text"), {"document_id": "docB"})

    results = store.query(org_id, provider.embed_text("policy text"), top_k=5, document_id="docA")
    assert len(results) == 1
    assert results[0].chunk_id == chunk_a


def test_faiss_vector_store_delete_removes_from_results():
    store = FAISSVectorStore(tempfile.mkdtemp())
    provider = FakeEmbeddingProvider(dimension=32)
    org_id = str(uuid.uuid4())
    chunk_id = str(uuid.uuid4())

    store.upsert(org_id, chunk_id, provider.embed_text("some content"), {"document_id": "docA"})
    assert len(store.query(org_id, provider.embed_text("some content"), top_k=5)) == 1

    store.delete(org_id, chunk_id)
    assert len(store.query(org_id, provider.embed_text("some content"), top_k=5)) == 0


def test_faiss_vector_store_query_on_unknown_org_returns_empty():
    store = FAISSVectorStore(tempfile.mkdtemp())
    provider = FakeEmbeddingProvider(dimension=32)
    results = store.query(str(uuid.uuid4()), provider.embed_text("anything"), top_k=5)
    assert results == []


def test_faiss_vector_store_persists_across_instances():
    index_dir = tempfile.mkdtemp()
    provider = FakeEmbeddingProvider(dimension=32)
    org_id = str(uuid.uuid4())
    chunk_id = str(uuid.uuid4())

    store1 = FAISSVectorStore(index_dir)
    store1.upsert(org_id, chunk_id, provider.embed_text("persisted content"), {"document_id": "docA"})

    # A fresh instance pointed at the same directory should load from disk.
    store2 = FAISSVectorStore(index_dir)
    results = store2.query(org_id, provider.embed_text("persisted content"), top_k=5)
    assert len(results) == 1
    assert results[0].chunk_id == chunk_id


def test_fake_llm_provider_returns_deterministic_string():
    provider = FakeLLMProvider()
    assert isinstance(provider.generate("any prompt"), str)
    assert provider.generate("prompt A") == provider.generate("prompt B")


def test_format_history_empty():
    assert format_history([]) == "(no prior messages)"


def test_format_history_renders_roles():
    history = [{"role": "user", "content": "Hi"}, {"role": "assistant", "content": "Hello!"}]
    rendered = format_history(history)
    assert "User: Hi" in rendered
    assert "Assistant: Hello!" in rendered


def test_format_context_empty():
    assert format_context([]) == "(no relevant context found)"


def test_build_rag_prompt_includes_question_context_and_history():
    prompt = build_rag_prompt(
        question="What is the vacation policy?",
        context_chunks=[{"content": "Employees get 20 days.", "source": "handbook.pdf"}],
        history=[{"role": "user", "content": "Hi"}],
    )
    assert "What is the vacation policy?" in prompt
    assert "Employees get 20 days." in prompt
    assert "handbook.pdf" in prompt
    assert "User: Hi" in prompt
