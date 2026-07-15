"""
Business logic for analytics.

Deliberately no `models.py` in this module: analytics is a read-only view
over data other modules already own (documents, chat, tickets, agent
runs) — introducing a parallel analytics-specific table would mean
keeping it in sync with the source of truth for no benefit. Every
function here is a query, never a write.

`estimated_ai_cost_usd` is explicitly a placeholder (flat rate × agent run
count) — see the comment on `Settings.AI_COST_PER_AGENT_RUN_USD`. Real
per-token costing requires usage metering this project doesn't have yet
(Ollama's API doesn't return token counts the way hosted APIs do).
"""
import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.modules.agents.models import AgentRun
from app.modules.chat.models import ChatMessage, Conversation
from app.modules.documents.models import Document, DocumentChunk, DocumentVersion
from app.modules.workflows.models import Ticket

settings = get_settings()


async def get_organization_overview(db: AsyncSession, org_id: uuid.UUID) -> dict:
    total_documents = (
        await db.execute(
            select(func.count(Document.id)).where(
                Document.organization_id == org_id, Document.deleted_at.is_(None)
            )
        )
    ).scalar_one()

    total_document_chunks = (
        await db.execute(
            select(func.count(DocumentChunk.id))
            .join(DocumentVersion, DocumentChunk.document_version_id == DocumentVersion.id)
            .join(Document, DocumentVersion.document_id == Document.id)
            .where(Document.organization_id == org_id, Document.deleted_at.is_(None))
        )
    ).scalar_one()

    total_conversations = (
        await db.execute(
            select(func.count(Conversation.id)).where(
                Conversation.organization_id == org_id, Conversation.deleted_at.is_(None)
            )
        )
    ).scalar_one()

    total_chat_messages = (
        await db.execute(
            select(func.count(ChatMessage.id))
            .join(Conversation, ChatMessage.conversation_id == Conversation.id)
            .where(Conversation.organization_id == org_id, Conversation.deleted_at.is_(None))
        )
    ).scalar_one()

    total_tickets = (
        await db.execute(
            select(func.count(Ticket.id)).where(
                Ticket.organization_id == org_id, Ticket.deleted_at.is_(None)
            )
        )
    ).scalar_one()

    tickets_by_status_rows = (
        await db.execute(
            select(Ticket.status, func.count(Ticket.id))
            .where(Ticket.organization_id == org_id, Ticket.deleted_at.is_(None))
            .group_by(Ticket.status)
        )
    ).all()
    tickets_by_status = {status: count for status, count in tickets_by_status_rows}

    total_agent_runs = (
        await db.execute(
            select(func.count(AgentRun.id)).where(AgentRun.organization_id == org_id)
        )
    ).scalar_one()

    agent_runs_by_route_rows = (
        await db.execute(
            select(AgentRun.route_taken, func.count(AgentRun.id))
            .where(AgentRun.organization_id == org_id)
            .group_by(AgentRun.route_taken)
        )
    ).all()
    agent_runs_by_route = {route: count for route, count in agent_runs_by_route_rows}

    avg_latency = (
        await db.execute(
            select(func.avg(AgentRun.latency_ms)).where(AgentRun.organization_id == org_id)
        )
    ).scalar_one()

    return {
        "total_documents": total_documents,
        "total_document_chunks": total_document_chunks,
        "total_conversations": total_conversations,
        "total_chat_messages": total_chat_messages,
        "total_tickets": total_tickets,
        "tickets_by_status": tickets_by_status,
        "total_agent_runs": total_agent_runs,
        "agent_runs_by_route": agent_runs_by_route,
        "avg_agent_latency_ms": float(avg_latency) if avg_latency is not None else None,
        "estimated_ai_cost_usd": round(total_agent_runs * settings.AI_COST_PER_AGENT_RUN_USD, 4),
    }
