import pytest

from app.core.notifications import FakeEmailProvider
from app.modules.auth.schemas import RegisterRequest
from app.modules.auth.service import register_user
from app.modules.organizations.schemas import InviteCreate, OrganizationCreate
from app.modules.organizations.service import (
    accept_invite,
    create_invite,
    create_organization,
)

pytestmark = pytest.mark.asyncio


async def test_full_invite_accept_flow(db_session):
    email_provider = FakeEmailProvider()
    owner, _ = await register_user(
        db_session,
        RegisterRequest(email="owner@svc.com", password="supersecret1", full_name="Owner"),
        email_provider,
    )
    invitee, _ = await register_user(
        db_session,
        RegisterRequest(email="invitee@svc.com", password="supersecret1", full_name="Invitee"),
        email_provider,
    )

    org = await create_organization(db_session, OrganizationCreate(name="Delta Co"), owner)

    invite = await create_invite(
        db_session, org.id, InviteCreate(email="invitee@svc.com", role="admin")
    )
    assert invite.accepted is False

    membership = await accept_invite(db_session, invite.token, invitee)
    assert membership.organization_id == org.id
    assert membership.user_id == invitee.id
    assert membership.role == "admin"


async def test_accept_invite_rejects_wrong_email(db_session):
    email_provider = FakeEmailProvider()
    owner, _ = await register_user(
        db_session,
        RegisterRequest(email="owner4@svc.com", password="supersecret1", full_name="Owner4"),
        email_provider,
    )
    stranger, _ = await register_user(
        db_session,
        RegisterRequest(email="stranger@svc.com", password="supersecret1", full_name="Stranger"),
        email_provider,
    )
    org = await create_organization(db_session, OrganizationCreate(name="Epsilon"), owner)
    invite = await create_invite(
        db_session, org.id, InviteCreate(email="intended@svc.com", role="member")
    )

    from fastapi import HTTPException

    with pytest.raises(HTTPException) as exc_info:
        await accept_invite(db_session, invite.token, stranger)
    assert exc_info.value.status_code == 403
