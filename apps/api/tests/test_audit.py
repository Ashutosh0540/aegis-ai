import pytest

pytestmark = pytest.mark.asyncio


async def _register_and_login(client, email):
    await client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": "supersecret1", "full_name": email.split("@")[0]},
    )
    login_resp = await client.post(
        "/api/v1/auth/login", data={"username": email, "password": "supersecret1"}
    )
    return login_resp.json()["access_token"]


def _auth(token):
    return {"Authorization": f"Bearer {token}"}


async def _create_org(client, token, name="Acme Corp"):
    resp = await client.post("/api/v1/organizations", json={"name": name}, headers=_auth(token))
    return resp.json()["id"]


async def test_every_api_request_is_logged(client):
    token = await _register_and_login(client, "audituser1@example.com")
    org_id = await _create_org(client, token)

    # The org-creation request itself and this list call should both be
    # picked up by the middleware.
    await client.get(f"/api/v1/organizations/{org_id}/tickets", headers=_auth(token))

    logs_resp = await client.get(f"/api/v1/organizations/{org_id}/audit-logs", headers=_auth(token))
    assert logs_resp.status_code == 200
    logs = logs_resp.json()
    api_request_logs = [l for l in logs if l["event_type"] == "api_request"]
    assert len(api_request_logs) >= 1
    assert any(l["path"].endswith("/tickets") for l in api_request_logs)


async def test_login_failure_is_logged_as_security_event(client, db_session):
    from sqlalchemy import select

    from app.modules.audit.models import AuditLog

    await _register_and_login(client, "audituser2@example.com")

    await client.post(
        "/api/v1/auth/login", data={"username": "audituser2@example.com", "password": "wrongpassword"}
    )

    # Login events precede any org context (a user isn't scoped to an org
    # until they create/join one), so organization_id is null here — this
    # verifies the row directly rather than via the org-scoped endpoint.
    result = await db_session.execute(
        select(AuditLog).where(AuditLog.event_type == "auth.login_failed")
    )
    logs = list(result.scalars().all())
    assert len(logs) >= 1
    assert logs[0].event_metadata["reason"] == "bad_password"


async def test_login_success_is_logged(client, db_session):
    from sqlalchemy import select

    from app.modules.audit.models import AuditLog

    await _register_and_login(client, "audituser3@example.com")

    result = await db_session.execute(
        select(AuditLog).where(AuditLog.event_type == "auth.login_succeeded")
    )
    logs = list(result.scalars().all())
    assert len(logs) >= 1


async def test_agent_invocation_is_logged_as_ai_action(client):
    token = await _register_and_login(client, "audituser4@example.com")
    org_id = await _create_org(client, token)

    await client.post(
        f"/api/v1/organizations/{org_id}/agents/invoke",
        json={"input": "hello there"},
        headers=_auth(token),
    )

    logs_resp = await client.get(
        f"/api/v1/organizations/{org_id}/audit-logs?event_type=agent.invoked", headers=_auth(token)
    )
    logs = logs_resp.json()
    assert len(logs) == 1
    assert logs[0]["event_metadata"]["route"] == "knowledge_agent"


async def test_member_cannot_view_audit_logs_only_admin_owner(client):
    owner_token = await _register_and_login(client, "auditowner5@example.com")
    member_token = await _register_and_login(client, "auditmember5@example.com")
    org_id = await _create_org(client, owner_token)

    resp = await client.get(f"/api/v1/organizations/{org_id}/audit-logs", headers=_auth(member_token))
    assert resp.status_code == 403


async def test_audit_logs_are_scoped_to_organization(client):
    token_a = await _register_and_login(client, "auditorga@example.com")
    token_b = await _register_and_login(client, "auditorgb@example.com")
    org_a = await _create_org(client, token_a, "Org A")
    org_b = await _create_org(client, token_b, "Org B")

    await client.get(f"/api/v1/organizations/{org_a}/tickets", headers=_auth(token_a))

    logs_b = await client.get(f"/api/v1/organizations/{org_b}/audit-logs", headers=_auth(token_b))
    org_a_logs = [l for l in logs_b.json() if l.get("organization_id") == org_a]
    assert org_a_logs == []
