"""
RAG prompt assembly — the actual LangChain usage in this codebase.

Milestone 3 is a single-pass "retrieve then generate" chain: embed the
question, retrieve top-k chunks, assemble one prompt, call the LLM once.
Multi-step reasoning (the agent deciding to search again, call a tool,
etc.) is explicitly LangGraph/Milestone 4 — this intentionally stays a
plain chain so that boundary is clean.
"""
from langchain_core.prompts import PromptTemplate

RAG_PROMPT_TEMPLATE = PromptTemplate.from_template(
    """You are AegisAI's knowledge assistant. Answer the user's question using ONLY the
context provided below. If the context doesn't contain the answer, say so plainly
rather than guessing. Be concise.

Conversation so far:
{history}

Retrieved context:
{context}

Question: {question}

Answer:"""
)


def format_history(messages: list[dict]) -> str:
    """`messages` is a list of {"role": "user"|"assistant", "content": str},
    most recent last. Formatted plainly since this goes straight into an LLM
    prompt, not rendered as UI."""
    if not messages:
        return "(no prior messages)"
    lines = [f"{m['role'].capitalize()}: {m['content']}" for m in messages]
    return "\n".join(lines)


def format_context(chunks: list[dict]) -> str:
    """`chunks` is a list of {"content": str, "source": str} — `source` is a
    human-readable reference (e.g. filename) so the LLM can naturally
    mention what it's drawing from, in addition to the structured citations
    stored separately in the ChatMessage row."""
    if not chunks:
        return "(no relevant context found)"
    blocks = [f"[Source: {c['source']}]\n{c['content']}" for c in chunks]
    return "\n\n---\n\n".join(blocks)


def build_rag_prompt(question: str, context_chunks: list[dict], history: list[dict]) -> str:
    return RAG_PROMPT_TEMPLATE.format(
        history=format_history(history),
        context=format_context(context_chunks),
        question=question,
    )
