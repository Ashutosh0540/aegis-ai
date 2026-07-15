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


async def test_overview_on_empty_org_returns_zeroes(client):
    token = await _register_and_login(client, "analyticsuser1@example.com")
    org_id = await _create_org(client, token)

    resp = await client.get(f"/api/v1/organizations/{org_id}/analytics/overview", headers=_auth(token))
    assert resp.status_code == 200
    body = resp.json()
    assert body["total_documents"] == 0
    assert body["total_tickets"] == 0
    assert body["total_agent_runs"] == 0
    assert body["avg_agent_latency_ms"] is None
    assert body["estimated_ai_cost_usd"] == 0.0


async def test_overview_reflects_documents_tickets_and_agent_runs(client):
    token = await _register_and_login(client, "analyticsuser2@example.com")
    org_id = await _create_org(client, token)

    files = {"file": ("report.txt", b"Some analytics test content. " * 20, "text/plain")}
    await client.post(f"/api/v1/organizations/{org_id}/documents", files=files, headers=_auth(token))

    await client.post(
        f"/api/v1/organizations/{org_id}/tickets",
        json={"title": "Bug", "description": "details", "priority": "high"},
        headers=_auth(token),
    )

    await client.post(
        f"/api/v1/organizations/{org_id}/agents/invoke",
        json={"input": "hello?"},
        headers=_auth(token),
    )

    resp = await client.get(f"/api/v1/organizations/{org_id}/analytics/overview", headers=_auth(token))
    body = resp.json()
    assert body["total_documents"] == 1
    assert body["total_document_chunks"] >= 1
    assert body["total_tickets"] == 1
    assert body["tickets_by_status"] == {"open": 1}
    assert body["total_agent_runs"] == 1
    assert body["agent_runs_by_route"] == {"knowledge_agent": 1}
    assert body["avg_agent_latency_ms"] is not None
    assert body["estimated_ai_cost_usd"] > 0


async def test_analytics_scoped_to_organization(client):
    token_a = await _register_and_login(client, "analyticsorga@example.com")
    token_b = await _register_and_login(client, "analyticsorgb@example.com")
    org_a = await _create_org(client, token_a, "Org A")
    org_b = await _create_org(client, token_b, "Org B")

    await client.post(
        f"/api/v1/organizations/{org_a}/tickets",
        json={"title": "Org A ticket", "description": "details"},
        headers=_auth(token_a),
    )

    resp_b = await client.get(
        f"/api/v1/organizations/{org_b}/analytics/overview", headers=_auth(token_b)
    )
    assert resp_b.json()["total_tickets"] == 0


async def test_non_member_cannot_view_analytics(client):
    owner_token = await _register_and_login(client, "analyticsowner4@example.com")
    outsider_token = await _register_and_login(client, "analyticsoutsider4@example.com")
    org_id = await _create_org(client, owner_token)

    resp = await client.get(
        f"/api/v1/organizations/{org_id}/analytics/overview", headers=_auth(outsider_token)
    )
    assert resp.status_code == 403
