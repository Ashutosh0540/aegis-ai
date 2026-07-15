"""
Multi-agent orchestration via LangGraph.

Three specialized agents behind one Supervisor node:

  supervisor → knowledge_agent  (RAG over documents, Milestone 3/4)
             → workflow_agent    (drafts a support ticket, Milestone 5)
             → email_agent       (drafts/sends an email, Milestone 5)

Every node stays pure/side-effect-free with respect to the database: a
node's job is to *decide* (route) or *produce a draft* (ticket_draft,
email_draft). Actually creating the Ticket row or sending the email is
the calling service layer's job (`chat/service.py`, `agents/service.py`)
— those layers have the DB session and injected providers a graph node
deliberately doesn't need. This keeps the graph testable with zero I/O
beyond the three provider protocols it already depends on.
"""
import re
from typing import TypedDict

from langgraph.graph import END, StateGraph

from aegis_ai_core.embeddings import EmbeddingProvider
from aegis_ai_core.llm import LLMProvider
from aegis_ai_core.prompts import build_rag_prompt
from aegis_ai_core.vector_store import VectorStoreBackend

NO_CONTEXT_ANSWER = (
    "I couldn't find relevant information in the knowledge base to answer that. "
    "Try rephrasing, or ask about a different document."
)

EMAIL_ADDRESS_PATTERN = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")

# Checked in order; the first match wins. Phrase-based email triggers are
# checked before single-word workflow triggers so "email me about this bug"
# doesn't get misrouted to the workflow agent on the word "bug".
EMAIL_TRIGGERS = ("send an email", "send email", "email to", "compose an email", "draft an email", "write an email")
WORKFLOW_TRIGGERS = ("create a ticket", "open a ticket", "file a ticket", "report a bug", "ticket", "bug", "broken", "not working", "issue with")

AVAILABLE_AGENTS = [
    {
        "name": "supervisor",
        "description": "Routes an incoming request to the appropriate specialized agent.",
    },
    {
        "name": "knowledge_agent",
        "description": (
            "Answers questions using retrieval-augmented generation over the "
            "organization's uploaded documents, with citations."
        ),
    },
    {
        "name": "workflow_agent",
        "description": "Drafts a support ticket from a request describing a problem or task.",
    },
    {
        "name": "email_agent",
        "description": (
            "Drafts an email from a request, and sends it if a recipient address "
            "can be identified in the message."
        ),
    },
    # Milestone 6 may add: meeting_agent, analytics_agent.
]


class AgentState(TypedDict, total=False):
    question: str
    organization_id: str
    document_id: str | None
    history: list[dict]
    top_k: int
    route: str
    context_chunks: list[dict]
    citations: list[dict]
    answer: str
    ticket_draft: dict | None
    email_draft: dict | None


def _classify_route(question: str) -> str:
    lowered = question.lower()
    if any(trigger in lowered for trigger in EMAIL_TRIGGERS):
        return "email_agent"
    if any(trigger in lowered for trigger in WORKFLOW_TRIGGERS):
        return "workflow_agent"
    return "knowledge_agent"


def _supervisor_node(state: AgentState) -> AgentState:
    """
    Routing step. Real keyword-based classification across three
    destinations (see `_classify_route`) — this is intentionally a simple
    rule-based classifier rather than an LLM call: it's fast, free, and
    deterministic, which matters for a routing decision that gates which
    side effects happen downstream. Replacing it with an LLM-based
    classifier later is a change contained entirely to this function.
    """
    return {**state, "route": _classify_route(state["question"])}


def _make_knowledge_agent_node(
    embedding_provider: EmbeddingProvider,
    vector_store: VectorStoreBackend,
    llm_provider: LLMProvider,
):
    def _knowledge_agent_node(state: AgentState) -> AgentState:
        question_vector = embedding_provider.embed_text(state["question"])
        matches = vector_store.query(
            organization_id=state["organization_id"],
            vector=question_vector,
            top_k=state.get("top_k", 5),
            document_id=state.get("document_id"),
        )

        if not matches:
            return {**state, "context_chunks": [], "citations": [], "answer": NO_CONTEXT_ANSWER}

        context_chunks = [
            {
                "content": m.metadata.get("content", ""),
                "source": m.metadata.get("filename", "unknown"),
            }
            for m in matches
        ]
        citations = [
            {
                "chunk_id": m.chunk_id,
                "document_id": m.metadata.get("document_id", ""),
                "document_version_id": m.metadata.get("document_version_id", ""),
                "chunk_index": m.metadata.get("chunk_index", -1),
                "filename": m.metadata.get("filename", "unknown"),
                "score": m.score,
            }
            for m in matches
        ]

        prompt = build_rag_prompt(state["question"], context_chunks, state.get("history", []))
        answer = llm_provider.generate(prompt)

        return {**state, "context_chunks": context_chunks, "citations": citations, "answer": answer}

    return _knowledge_agent_node


def _workflow_agent_node(state: AgentState) -> AgentState:
    """
    Drafts a ticket from the request. Does NOT create the Ticket row
    itself — returns `ticket_draft` for the calling service layer (which
    has a DB session and the n8n client) to persist via
    `workflows.service.create_ticket_from_agent_draft`.
    """
    question = state["question"].strip()
    title = question[:120] if question else "Untitled ticket"
    draft = {"title": title, "description": question, "priority": "medium"}
    answer = f'I\'ve drafted a ticket to track this: "{title}".'
    return {**state, "ticket_draft": draft, "citations": [], "answer": answer}


def _make_email_agent_node(llm_provider: LLMProvider):
    def _email_agent_node(state: AgentState) -> AgentState:
        question = state["question"]
        recipient_match = EMAIL_ADDRESS_PATTERN.search(question)
        recipient = recipient_match.group(0) if recipient_match else None

        prompt = (
            "Draft a professional, concise email body for this request. "
            "Write only the email body, no subject line.\n\n"
            f"Request: {question}"
        )
        body = llm_provider.generate(prompt)
        subject = f"Message from AegisAI: {question[:60]}"
        draft = {"to": recipient, "subject": subject, "body": body}

        if recipient:
            answer = f"I've drafted and sent an email to {recipient}."
        else:
            answer = (
                "I've drafted an email, but couldn't find a recipient address in your "
                f"message — here's the draft:\n\n{body}"
            )

        return {**state, "email_draft": draft, "citations": [], "answer": answer}

    return _email_agent_node


def _route_selector(state: AgentState) -> str:
    return state.get("route", "knowledge_agent")


def build_supervisor_graph(
    embedding_provider: EmbeddingProvider,
    vector_store: VectorStoreBackend,
    llm_provider: LLMProvider,
):
    """
    Compile the Supervisor → {knowledge_agent, workflow_agent, email_agent}
    graph. Cheap to call per request (no heavy compilation cost) since the
    real cost lives in the provider calls a node makes, not in graph
    construction — callers don't need to cache the compiled graph across
    requests.
    """
    knowledge_agent_node = _make_knowledge_agent_node(embedding_provider, vector_store, llm_provider)
    email_agent_node = _make_email_agent_node(llm_provider)

    graph = StateGraph(AgentState)
    graph.add_node("supervisor", _supervisor_node)
    graph.add_node("knowledge_agent", knowledge_agent_node)
    graph.add_node("workflow_agent", _workflow_agent_node)
    graph.add_node("email_agent", email_agent_node)
    graph.set_entry_point("supervisor")
    graph.add_conditional_edges(
        "supervisor",
        _route_selector,
        {
            "knowledge_agent": "knowledge_agent",
            "workflow_agent": "workflow_agent",
            "email_agent": "email_agent",
        },
    )
    graph.add_edge("knowledge_agent", END)
    graph.add_edge("workflow_agent", END)
    graph.add_edge("email_agent", END)
    return graph.compile()


def run_supervisor_graph(
    question: str,
    organization_id: str,
    embedding_provider: EmbeddingProvider,
    vector_store: VectorStoreBackend,
    llm_provider: LLMProvider,
    document_id: str | None = None,
    history: list[dict] | None = None,
    top_k: int = 5,
) -> AgentState:
    """Convenience wrapper: build + invoke the graph in one call, returning
    the final state (route taken, answer, citations, and any ticket/email
    draft for the caller to act on)."""
    graph = build_supervisor_graph(embedding_provider, vector_store, llm_provider)
    initial_state: AgentState = {
        "question": question,
        "organization_id": organization_id,
        "document_id": document_id,
        "history": history or [],
        "top_k": top_k,
    }
    return graph.invoke(
        initial_state,
        config={
            "run_name": "supervisor_graph",
            "tags": ["aegis-ai", "supervisor"],
            "metadata": {"organization_id": organization_id},
        },
    )
