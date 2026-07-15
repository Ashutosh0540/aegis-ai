"""Business logic for organizations, membership, and invites."""
import re
import secrets
import uuid

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.organizations.models import (
    Organization,
    OrganizationInvite,
    OrganizationMember,
    OrgRole,
)
from app.modules.organizations.schemas import InviteCreate, OrganizationCreate
from app.modules.users.models import User
from app.modules.users.service import get_user_by_email


def _slugify(name: str) -> str:
    base = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
    return f"{base}-{secrets.token_hex(3)}"


async def create_organization(
    db: AsyncSession, payload: OrganizationCreate, owner: User
) -> Organization:
    org = Organization(name=payload.name, slug=_slugify(payload.name))
    db.add(org)
    await db.flush()  # obtain org.id before creating the membership row

    membership = OrganizationMember(
        organization_id=org.id, user_id=owner.id, role=OrgRole.OWNER.value
    )
    db.add(membership)
    await db.commit()
    await db.refresh(org)
    return org


async def list_user_organizations(db: AsyncSession, user_id: uuid.UUID) -> list[Organization]:
    result = await db.execute(
        select(Organization)
        .join(OrganizationMember, OrganizationMember.organization_id == Organization.id)
        .where(
            OrganizationMember.user_id == user_id,
            OrganizationMember.deleted_at.is_(None),
            Organization.deleted_at.is_(None),
        )
    )
    return list(result.scalars().all())


async def create_invite(
    db: AsyncSession, org_id: uuid.UUID, payload: InviteCreate
) -> OrganizationInvite:
    existing = await db.execute(
        select(OrganizationInvite).where(
            OrganizationInvite.organization_id == org_id,
            OrganizationInvite.email == payload.email.lower(),
            OrganizationInvite.accepted.is_(False),
            OrganizationInvite.deleted_at.is_(None),
        )
    )
    if existing.scalar_one_or_none() is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="An active invite for this email already exists",
        )

    invite = OrganizationInvite(
        organization_id=org_id,
        email=payload.email.lower(),
        role=payload.role.value,
        token=secrets.token_urlsafe(32),
    )
    db.add(invite)
    await db.commit()
    await db.refresh(invite)
    # NOTE: actual email delivery is wired in a later milestone via the
    # notification/email agent. For now the invite record + token is the
    # source of truth and can be sent manually or via SMTP stub.
    return invite


async def accept_invite(db: AsyncSession, token: str, user: User) -> OrganizationMember:
    result = await db.execute(
        select(OrganizationInvite).where(
            OrganizationInvite.token == token,
            OrganizationInvite.accepted.is_(False),
            OrganizationInvite.deleted_at.is_(None),
        )
    )
    invite = result.scalar_one_or_none()
    if invite is None:
        raise HTTPException(status_code=404, detail="Invite not found or already used")

    if invite.email.lower() != user.email.lower():
        raise HTTPException(
            status_code=403, detail="This invite was issued to a different email address"
        )

    membership = OrganizationMember(
        organization_id=invite.organization_id, user_id=user.id, role=invite.role
    )
    invite.accepted = True
    db.add(membership)
    await db.commit()
    await db.refresh(membership)
    return membership
