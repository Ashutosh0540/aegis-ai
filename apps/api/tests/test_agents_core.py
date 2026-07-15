import tempfile
import uuid

from aegis_ai_core.agents import AVAILABLE_AGENTS, build_supervisor_graph, run_supervisor_graph
from aegis_ai_core.embeddings import FakeEmbeddingProvider
from aegis_ai_core.llm import FakeLLMProvider
from aegis_ai_core.vector_store import FAISSVectorStore


def _seeded_store():
    store = FAISSVectorStore(tempfile.mkdtemp())
    provider = FakeEmbeddingProvider(dimension=32)
    org_id = str(uuid.uuid4())
    chunk_id = str(uuid.uuid4())
    store.upsert(
        org_id,
        chunk_id,
        provider.embed_text("the vacation policy grants 20 days per year"),
        {
            "document_id": "docA",
            "document_version_id": "verA",
            "chunk_index": 0,
            "content": "the vacation policy grants 20 days per year",
            "filename": "handbook.txt",
        },
    )
    return store, provider, org_id, chunk_id


def test_available_agents_lists_supervisor_and_knowledge_agent():
    names = {a["name"] for a in AVAILABLE_AGENTS}
    assert "supervisor" in names
    assert "knowledge_agent" in names


def test_supervisor_routes_to_knowledge_agent():
    store, provider, org_id, _ = _seeded_store()
    llm = FakeLLMProvider()

    result = run_supervisor_graph("vacation days?", org_id, provider, store, llm)
    assert result["route"] == "knowledge_agent"


def test_knowledge_agent_returns_answer_and_citations_when_context_found():
    store, provider, org_id, chunk_id = _seeded_store()
    llm = FakeLLMProvider()

    result = run_supervisor_graph("how many vacation days?", org_id, provider, store, llm)
    assert result["answer"]
    assert len(result["citations"]) == 1
    assert result["citations"][0]["chunk_id"] == chunk_id
    assert result["citations"][0]["filename"] == "handbook.txt"


def test_knowledge_agent_returns_no_context_answer_when_nothing_found():
    store = FAISSVectorStore(tempfile.mkdtemp())
    provider = FakeEmbeddingProvider(dimension=32)
    llm = FakeLLMProvider()
    empty_org = str(uuid.uuid4())

    result = run_supervisor_graph("anything at all?", empty_org, provider, store, llm)
    assert result["citations"] == []
    assert "couldn't find" in result["answer"].lower()


def test_knowledge_agent_respects_document_id_scope():
    store = FAISSVectorStore(tempfile.mkdtemp())
    provider = FakeEmbeddingProvider(dimension=32)
    llm = FakeLLMProvider()
    org_id = str(uuid.uuid4())

    store.upsert(
        org_id, str(uuid.uuid4()), provider.embed_text("refund policy details"),
        {"document_id": "docA", "content": "refund policy details", "filename": "a.txt"},
    )
    store.upsert(
        org_id, str(uuid.uuid4()), provider.embed_text("refund policy details"),
        {"document_id": "docB", "content": "refund policy details", "filename": "b.txt"},
    )

    result = run_supervisor_graph(
        "refund policy?", org_id, provider, store, llm, document_id="docA"
    )
    assert all(c["document_id"] == "docA" for c in result["citations"])


def test_build_supervisor_graph_is_reusable_across_invocations():
    store, provider, org_id, _ = _seeded_store()
    llm = FakeLLMProvider()
    graph = build_supervisor_graph(provider, store, llm)

    result1 = graph.invoke({"question": "vacation days?", "organization_id": org_id})
    result2 = graph.invoke({"question": "vacation days again?", "organization_id": org_id})
    assert result1["route"] == result2["route"] == "knowledge_agent"
