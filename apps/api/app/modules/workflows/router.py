"""HTTP routes for /api/v1/organizations/{org_id}/tickets."""
import uuid

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.deps import RequireOrgRole, get_current_active_user
from app.core.n8n_client import N8nClient, get_n8n_client
from app.modules.organizations.models import OrgRole
from app.modules.users.models import User
from app.modules.workflows import service
from app.modules.workflows.schemas import TicketCreate, TicketRead, TicketUpdate

router = APIRouter(prefix="/organizations/{org_id}/tickets", tags=["workflows"])

_any_member = RequireOrgRole(OrgRole.OWNER.value, OrgRole.ADMIN.value, OrgRole.MEMBER.value)


@router.post("", response_model=TicketRead, status_code=201, dependencies=[Depends(_any_member)])
async def create_ticket(
    org_id: uuid.UUID,
    payload: TicketCreate,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
    n8n_client: N8nClient = Depends(get_n8n_client),
):
    return await service.create_ticket(db, org_id, current_user.id, payload, n8n_client)


@router.get("", response_model=list[TicketRead], dependencies=[Depends(_any_member)])
async def list_tickets(org_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    return await service.list_tickets(db, org_id)


@router.get("/{ticket_id}", response_model=TicketRead, dependencies=[Depends(_any_member)])
async def get_ticket(org_id: uuid.UUID, ticket_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    return await service.get_ticket(db, org_id, ticket_id)


@router.patch("/{ticket_id}", response_model=TicketRead, dependencies=[Depends(_any_member)])
async def update_ticket(
    org_id: uuid.UUID,
    ticket_id: uuid.UUID,
    payload: TicketUpdate,
    db: AsyncSession = Depends(get_db),
):
    ticket = await service.get_ticket(db, org_id, ticket_id)
    return await service.update_ticket(db, ticket, payload)
