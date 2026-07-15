import uuid

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.deps import RequireOrgRole, get_current_active_user
from app.modules.organizations import service
from app.modules.organizations.models import OrgRole
from app.modules.organizations.schemas import (
    InviteAccept,
    InviteCreate,
    InviteRead,
    OrganizationCreate,
    OrganizationRead,
)
from app.modules.users.models import User

router = APIRouter(prefix="/organizations", tags=["organizations"])


@router.post("", response_model=OrganizationRead, status_code=201)
async def create_organization(
    payload: OrganizationCreate,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    return await service.create_organization(db, payload, current_user)


@router.get("", response_model=list[OrganizationRead])
async def list_my_organizations(
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    return await service.list_user_organizations(db, current_user.id)


@router.post(
    "/{org_id}/invites",
    response_model=InviteRead,
    status_code=201,
    dependencies=[Depends(RequireOrgRole(OrgRole.OWNER.value, OrgRole.ADMIN.value))],
)
async def invite_member(
    org_id: uuid.UUID,
    payload: InviteCreate,
    db: AsyncSession = Depends(get_db),
):
    return await service.create_invite(db, org_id, payload)


@router.post("/invites/accept", status_code=201)
async def accept_invite(
    payload: InviteAccept,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    membership = await service.accept_invite(db, payload.token, current_user)
    return {"organization_id": str(membership.organization_id), "role": membership.role}
