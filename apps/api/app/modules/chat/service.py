"""
Business logic for chat: conversation management, backed by the shared
Supervisor/Knowledge/Workflow/Email Agent LangGraph graph for actual
answer generation and, where the graph routes to workflow_agent or
email_agent, real side effects (ticket creation, email send) via
`app.core.agent_side_effects`.

`post_message` persists the user's turn, pulls recent history as memory,
and delegates retrieval + generation to `aegis_ai_core.agents.
run_supervisor_graph` — the same graph the `agents` module exposes for
ad-hoc invocation. Milestone 3's plain retrieve-then-generate chain now
lives inside that graph's `knowledge_agent` node rather than here; this
function's inputs/outputs are unchanged, only the internals moved.
"""
import uuid

from aegis_ai_core.agents import run_supervisor_graph
from aegis_ai_core.embeddings import EmbeddingProvider
from aegis_ai_core.llm import LLMProvider
from aegis_ai_core.vector_store import VectorStoreBackend
from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.agent_side_effects import apply_agent_side_effects
from app.core.config import get_settings
from app.core.n8n_client import N8nClient
from app.core.notifications import EmailProvider
from app.modules.chat.models import ChatMessage, Conversation, MessageRole
from app.modules.chat.schemas import ChatMessageCreate, ConversationCreate

settings = get_settings()


async def create_conversation(
    db: AsyncSession, org_id: uuid.UUID, created_by_id: uuid.UUID, payload: ConversationCreate
) -> Conversation:
    conversation = Conversation(
        organization_id=org_id,
        created_by_id=created_by_id,
        title=payload.title,
        document_id=payload.document_id,
    )
    db.add(conversation)
    await db.commit()
    await db.refresh(conversation)
    return conversation


async def list_conversations(db: AsyncSession, org_id: uuid.UUID) -> list[Conversation]:
    result = await db.execute(
        select(Conversation)
        .where(Conversation.organization_id == org_id, Conversation.deleted_at.is_(None))
        .order_by(Conversation.created_at.desc())
    )
    return list(result.scalars().all())


async def get_conversation(
    db: AsyncSession, org_id: uuid.UUID, conversation_id: uuid.UUID
) -> Conversation:
    result = await db.execute(
        select(Conversation).where(
            Conversation.id == conversation_id,
            Conversation.organization_id == org_id,
            Conversation.deleted_at.is_(None),
        )
    )
    conversation = result.scalar_one_or_none()
    if conversation is None:
        raise HTTPException(status_code=404, detail="Conversation not found")
    return conversation


async def list_messages(db: AsyncSession, conversation_id: uuid.UUID) -> list[ChatMessage]:
    result = await db.execute(
        select(ChatMessage)
        .where(ChatMessage.conversation_id == conversation_id)
        .order_by(ChatMessage.created_at)
    )
    return list(result.scalars().all())


async def post_message(
    db: AsyncSession,
    conversation: Conversation,
    payload: ChatMessageCreate,
    sender_id: uuid.UUID,
    embedding_provider: EmbeddingProvider,
    vector_store: VectorStoreBackend,
    llm_provider: LLMProvider,
    notification_provider: EmailProvider,
    n8n_client: N8nClient,
) -> ChatMessage:
    # 1. Persist the user's message first — it's part of history/audit
    #    regardless of whether generation succeeds.
    user_message = ChatMessage(
        conversation_id=conversation.id, role=MessageRole.USER.value, content=payload.content
    )
    db.add(user_message)
    await db.flush()

    # 2. Pull recent history (memory) — everything except the message we
    #    just added, most recent last, capped to keep the prompt bounded.
    history_result = await db.execute(
        select(ChatMessage)
        .where(ChatMessage.conversation_id == conversation.id, ChatMessage.id != user_message.id)
        .order_by(ChatMessage.created_at.desc())
        .limit(settings.RAG_HISTORY_MESSAGE_LIMIT)
    )
    history = [
        {"role": m.role, "content": m.content} for m in reversed(list(history_result.scalars().all()))
    ]

    # 3. Run the Supervisor graph — it decides which agent handles this
    #    turn (knowledge/workflow/email) and, for knowledge_agent, does
    #    retrieval + generation inline (see aegis_ai_core.agents).
    result = run_supervisor_graph(
        question=payload.content,
        organization_id=str(conversation.organization_id),
        embedding_provider=embedding_provider,
        vector_store=vector_store,
        llm_provider=llm_provider,
        document_id=str(conversation.document_id) if conversation.document_id else None,
        history=history,
        top_k=settings.RAG_TOP_K,
    )

    # 4. Turn a workflow_agent/email_agent route into a real side effect
    #    (create the Ticket row, send the email).
    answer = await apply_agent_side_effects(
        db, result, conversation.organization_id, sender_id, notification_provider, n8n_client
    )

    from app.modules.audit.service import record_event

    await record_event(
        db,
        "agent.invoked",
        organization_id=conversation.organization_id,
        user_id=sender_id,
        resource_type="conversation",
        resource_id=str(conversation.id),
        event_metadata={"route": result.get("route", "unknown")},
    )

    assistant_message = ChatMessage(
        conversation_id=conversation.id,
        role=MessageRole.ASSISTANT.value,
        content=answer,
        citations=result.get("citations", []),
    )
    db.add(assistant_message)
    await db.commit()
    await db.refresh(assistant_message)
    return assistant_message
