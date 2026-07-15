"""
Business logic for workflows: ticket CRUD, and the n8n integration point.

`create_ticket` is the single path both the direct API (`POST
.../tickets`) and the Workflow Agent (via `create_ticket_from_agent_draft`)
go through — so both get the same n8n webhook trigger and the same
validation, rather than the agent path being a special case.
"""
import uuid

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.n8n_client import N8nClient
from app.modules.workflows.models import Ticket, TicketSource
from app.modules.workflows.schemas import TicketCreate, TicketUpdate


async def create_ticket(
    db: AsyncSession,
    org_id: uuid.UUID,
    created_by_id: uuid.UUID,
    payload: TicketCreate,
    n8n_client: N8nClient,
    source: str = TicketSource.MANUAL.value,
) -> Ticket:
    ticket = Ticket(
        organization_id=org_id,
        created_by_id=created_by_id,
        title=payload.title,
        description=payload.description,
        priority=payload.priority.value,
        source=source,
    )
    db.add(ticket)
    await db.commit()
    await db.refresh(ticket)

    n8n_client.trigger_webhook(
        "ticket.created",
        {
            "ticket_id": str(ticket.id),
            "organization_id": str(org_id),
            "title": ticket.title,
            "priority": ticket.priority,
            "source": ticket.source,
        },
    )

    return ticket


async def create_ticket_from_agent_draft(
    db: AsyncSession,
    org_id: uuid.UUID,
    created_by_id: uuid.UUID,
    ticket_draft: dict,
    n8n_client: N8nClient,
) -> Ticket:
    """Entry point used by the Workflow Agent (see chat/agents service
    layers) — takes the graph's drafted title/description and creates a
    real ticket through the same path a direct API call would use."""
    payload = TicketCreate(
        title=ticket_draft.get("title", "Untitled ticket")[:500],
        description=ticket_draft.get("description", ""),
        priority=ticket_draft.get("priority", "medium"),
    )
    return await create_ticket(
        db, org_id, created_by_id, payload, n8n_client, source=TicketSource.AGENT.value
    )


async def list_tickets(db: AsyncSession, org_id: uuid.UUID) -> list[Ticket]:
    result = await db.execute(
        select(Ticket)
        .where(Ticket.organization_id == org_id, Ticket.deleted_at.is_(None))
        .order_by(Ticket.created_at.desc())
    )
    return list(result.scalars().all())


async def get_ticket(db: AsyncSession, org_id: uuid.UUID, ticket_id: uuid.UUID) -> Ticket:
    result = await db.execute(
        select(Ticket).where(
            Ticket.id == ticket_id, Ticket.organization_id == org_id, Ticket.deleted_at.is_(None)
        )
    )
    ticket = result.scalar_one_or_none()
    if ticket is None:
        raise HTTPException(status_code=404, detail="Ticket not found")
    return ticket


async def update_ticket(db: AsyncSession, ticket: Ticket, payload: TicketUpdate) -> Ticket:
    if payload.status is not None:
        ticket.status = payload.status.value
    if payload.priority is not None:
        ticket.priority = payload.priority.value
    if payload.assigned_to_id is not None:
        ticket.assigned_to_id = payload.assigned_to_id
    await db.commit()
    await db.refresh(ticket)
    return ticket
