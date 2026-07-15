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


async def _upload_document(client, token, org_id, filename, content: bytes):
    files = {"file": (filename, content, "text/plain")}
    resp = await client.post(
        f"/api/v1/organizations/{org_id}/documents", files=files, headers=_auth(token)
    )
    assert resp.status_code == 201
    return resp.json()["id"]


async def test_list_agents_is_not_org_scoped_and_requires_no_membership(client):
    resp = await client.get("/api/v1/agents")
    assert resp.status_code == 200
    names = {a["name"] for a in resp.json()}
    assert "supervisor" in names
    assert "knowledge_agent" in names


async def test_invoke_agent_returns_answer_with_citations(client):
    token = await _register_and_login(client, "agentuser1@example.com")
    org_id = await _create_org(client, token)
    await _upload_document(
        client, token, org_id, "handbook.txt",
        b"The vacation policy grants 20 days of paid leave per year. " * 20,
    )

    resp = await client.post(
        f"/api/v1/organizations/{org_id}/agents/invoke",
        json={"input": "How many vacation days do I get?"},
        headers=_auth(token),
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["agent_name"] == "supervisor"
    assert body["route_taken"] == "knowledge_agent"
    assert body["status"] == "success"
    assert body["output_text"]
    assert len(body["citations"]) > 0
    assert body["latency_ms"] >= 0


async def test_invoke_agent_with_no_matching_documents_still_succeeds(client):
    token = await _register_and_login(client, "agentuser2@example.com")
    org_id = await _create_org(client, token)

    resp = await client.post(
        f"/api/v1/organizations/{org_id}/agents/invoke",
        json={"input": "anything at all?"},
        headers=_auth(token),
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["status"] == "success"
    assert body["citations"] == []
    assert "couldn't find" in body["output_text"].lower()


async def test_agent_runs_are_recorded_and_listable(client):
    token = await _register_and_login(client, "agentuser3@example.com")
    org_id = await _create_org(client, token)

    await client.post(
        f"/api/v1/organizations/{org_id}/agents/invoke",
        json={"input": "first question"},
        headers=_auth(token),
    )
    await client.post(
        f"/api/v1/organizations/{org_id}/agents/invoke",
        json={"input": "second question"},
        headers=_auth(token),
    )

    runs_resp = await client.get(
        f"/api/v1/organizations/{org_id}/agents/runs", headers=_auth(token)
    )
    assert runs_resp.status_code == 200
    runs = runs_resp.json()
    assert len(runs) == 2
    inputs = {r["input_text"] for r in runs}
    assert inputs == {"first question", "second question"}


async def test_non_member_cannot_invoke_agent(client):
    owner_token = await _register_and_login(client, "agentowner4@example.com")
    outsider_token = await _register_and_login(client, "agentoutsider4@example.com")
    org_id = await _create_org(client, owner_token)

    resp = await client.post(
        f"/api/v1/organizations/{org_id}/agents/invoke",
        json={"input": "hello?"},
        headers=_auth(outsider_token),
    )
    assert resp.status_code == 403


async def test_agent_runs_are_scoped_to_organization(client):
    token_a = await _register_and_login(client, "agentorga@example.com")
    token_b = await _register_and_login(client, "agentorgb@example.com")
    org_a = await _create_org(client, token_a, "Org A")
    org_b = await _create_org(client, token_b, "Org B")

    await client.post(
        f"/api/v1/organizations/{org_a}/agents/invoke",
        json={"input": "org A question"},
        headers=_auth(token_a),
    )

    runs_resp_b = await client.get(
        f"/api/v1/organizations/{org_b}/agents/runs", headers=_auth(token_b)
    )
    assert runs_resp_b.json() == []
