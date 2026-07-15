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


async def test_create_ticket_triggers_n8n_webhook(client, fake_n8n_client):
    token = await _register_and_login(client, "ticketuser1@example.com")
    org_id = await _create_org(client, token)

    resp = await client.post(
        f"/api/v1/organizations/{org_id}/tickets",
        json={"title": "Login page is broken", "description": "Users can't log in", "priority": "high"},
        headers=_auth(token),
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["title"] == "Login page is broken"
    assert body["status"] == "open"
    assert body["priority"] == "high"
    assert body["source"] == "manual"

    assert len(fake_n8n_client.triggered) == 1
    assert fake_n8n_client.triggered[0]["event"] == "ticket.created"
    assert fake_n8n_client.triggered[0]["payload"]["ticket_id"] == body["id"]


async def test_list_and_get_ticket(client):
    token = await _register_and_login(client, "ticketuser2@example.com")
    org_id = await _create_org(client, token)

    create_resp = await client.post(
        f"/api/v1/organizations/{org_id}/tickets",
        json={"title": "Bug report", "description": "Something's wrong"},
        headers=_auth(token),
    )
    ticket_id = create_resp.json()["id"]

    list_resp = await client.get(f"/api/v1/organizations/{org_id}/tickets", headers=_auth(token))
    assert len(list_resp.json()) == 1

    get_resp = await client.get(
        f"/api/v1/organizations/{org_id}/tickets/{ticket_id}", headers=_auth(token)
    )
    assert get_resp.status_code == 200
    assert get_resp.json()["id"] == ticket_id


async def test_update_ticket_status_and_priority(client):
    token = await _register_and_login(client, "ticketuser3@example.com")
    org_id = await _create_org(client, token)

    create_resp = await client.post(
        f"/api/v1/organizations/{org_id}/tickets",
        json={"title": "Server down", "description": "Prod outage"},
        headers=_auth(token),
    )
    ticket_id = create_resp.json()["id"]

    update_resp = await client.patch(
        f"/api/v1/organizations/{org_id}/tickets/{ticket_id}",
        json={"status": "in_progress", "priority": "urgent"},
        headers=_auth(token),
    )
    assert update_resp.status_code == 200
    body = update_resp.json()
    assert body["status"] == "in_progress"
    assert body["priority"] == "urgent"


async def test_tickets_are_scoped_to_organization(client):
    token_a = await _register_and_login(client, "ticketorga@example.com")
    token_b = await _register_and_login(client, "ticketorgb@example.com")
    org_a = await _create_org(client, token_a, "Org A")
    org_b = await _create_org(client, token_b, "Org B")

    await client.post(
        f"/api/v1/organizations/{org_a}/tickets",
        json={"title": "Org A issue", "description": "details"},
        headers=_auth(token_a),
    )

    list_resp_b = await client.get(f"/api/v1/organizations/{org_b}/tickets", headers=_auth(token_b))
    assert list_resp_b.json() == []


async def test_non_member_cannot_create_ticket(client):
    owner_token = await _register_and_login(client, "ticketowner4@example.com")
    outsider_token = await _register_and_login(client, "ticketoutsider4@example.com")
    org_id = await _create_org(client, owner_token)

    resp = await client.post(
        f"/api/v1/organizations/{org_id}/tickets",
        json={"title": "Should fail", "description": "no access"},
        headers=_auth(outsider_token),
    )
    assert resp.status_code == 403


async def test_get_nonexistent_ticket_404s(client):
    token = await _register_and_login(client, "ticketuser5@example.com")
    org_id = await _create_org(client, token)
    import uuid

    resp = await client.get(
        f"/api/v1/organizations/{org_id}/tickets/{uuid.uuid4()}", headers=_auth(token)
    )
    assert resp.status_code == 404


async def test_chat_message_about_a_bug_creates_a_real_ticket(client, fake_n8n_client):
    token = await _register_and_login(client, "workflowchat1@example.com")
    org_id = await _create_org(client, token)

    conv_resp = await client.post(
        f"/api/v1/organizations/{org_id}/chat/conversations", json={}, headers=_auth(token)
    )
    conversation_id = conv_resp.json()["id"]

    message_resp = await client.post(
        f"/api/v1/organizations/{org_id}/chat/conversations/{conversation_id}/messages",
        json={"content": "There's a bug on the checkout page, payments are failing"},
        headers=_auth(token),
    )
    assert message_resp.status_code == 201
    assert "Ticket #" in message_resp.json()["content"]

    tickets_resp = await client.get(f"/api/v1/organizations/{org_id}/tickets", headers=_auth(token))
    tickets = tickets_resp.json()
    assert len(tickets) == 1
    assert tickets[0]["source"] == "agent"
    assert any(t["event"] == "ticket.created" for t in fake_n8n_client.triggered)


async def test_chat_message_to_send_email_actually_sends_via_provider(client, fake_email_provider):
    token = await _register_and_login(client, "emailchat1@example.com")
    org_id = await _create_org(client, token)

    conv_resp = await client.post(
        f"/api/v1/organizations/{org_id}/chat/conversations", json={}, headers=_auth(token)
    )
    conversation_id = conv_resp.json()["id"]

    message_resp = await client.post(
        f"/api/v1/organizations/{org_id}/chat/conversations/{conversation_id}/messages",
        json={"content": "Please send an email to teammate@example.com about the roadmap update"},
        headers=_auth(token),
    )
    assert message_resp.status_code == 201
    assert "teammate@example.com" in message_resp.json()["content"]

    # fake_email_provider also received the registration email, so filter.
    sent_to_teammate = [e for e in fake_email_provider.sent_emails if e["to"] == "teammate@example.com"]
    assert len(sent_to_teammate) == 1


async def test_chat_message_to_email_without_recipient_only_drafts(client, fake_email_provider):
    token = await _register_and_login(client, "emailchat2@example.com")
    org_id = await _create_org(client, token)

    conv_resp = await client.post(
        f"/api/v1/organizations/{org_id}/chat/conversations", json={}, headers=_auth(token)
    )
    conversation_id = conv_resp.json()["id"]

    before_count = len(fake_email_provider.sent_emails)

    message_resp = await client.post(
        f"/api/v1/organizations/{org_id}/chat/conversations/{conversation_id}/messages",
        json={"content": "Can you draft an email about the new pricing plan?"},
        headers=_auth(token),
    )
    assert message_resp.status_code == 201
    assert "draft" in message_resp.json()["content"].lower()
    # No new send — only a draft since no recipient was parseable.
    assert len(fake_email_provider.sent_emails) == before_count


async def test_agent_invoke_bug_report_creates_ticket_via_agents_endpoint(client, fake_n8n_client):
    token = await _register_and_login(client, "workflowagent1@example.com")
    org_id = await _create_org(client, token)

    resp = await client.post(
        f"/api/v1/organizations/{org_id}/agents/invoke",
        json={"input": "Report a bug: the search feature returns no results"},
        headers=_auth(token),
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["route_taken"] == "workflow_agent"
    assert "Ticket #" in body["output_text"]

    tickets_resp = await client.get(f"/api/v1/organizations/{org_id}/tickets", headers=_auth(token))
    assert len(tickets_resp.json()) == 1
