"""
Turns a Supervisor graph result into real side effects.

The graph itself (`aegis_ai_core.agents`) only ever *decides* — a
`workflow_agent` route produces a `ticket_draft` dict, an `email_agent`
route produces an `email_draft` dict, neither touches a database or sends
anything. This module is where "decide" becomes "act": create the actual
`Ticket` row, send the actual email. Both `chat.service.post_message`
(conversational entry point) and `agents.service.invoke_agent` (ad-hoc
entry point) call this so a ticket/email request behaves identically
regardless of which one triggered the graph.
"""
import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.n8n_client import N8nClient
from app.core.notifications import EmailProvider


async def apply_agent_side_effects(
    db: AsyncSession,
    result: dict,
    org_id: uuid.UUID,
    user_id: uuid.UUID,
    notification_provider: EmailProvider,
    n8n_client: N8nClient,
) -> str:
    """Returns the final answer text — unchanged unless a ticket was
    created, in which case a short confirmation note is appended."""
    answer = result.get("answer", "")

    ticket_draft = result.get("ticket_draft")
    if ticket_draft:
        from app.modules.workflows.service import create_ticket_from_agent_draft

        ticket = await create_ticket_from_agent_draft(
            db, org_id, user_id, ticket_draft, n8n_client
        )
        answer = f"{answer} (Ticket #{str(ticket.id)[:8]} created.)"

    email_draft = result.get("email_draft")
    if email_draft and email_draft.get("to"):
        notification_provider.send_email(
            to=email_draft["to"], subject=email_draft["subject"], body=email_draft["body"]
        )

    return answer
