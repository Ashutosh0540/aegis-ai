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


async def test_create_and_list_conversations(client):
    token = await _register_and_login(client, "chatuser1@example.com")
    org_id = await _create_org(client, token)

    create_resp = await client.post(
        f"/api/v1/organizations/{org_id}/chat/conversations",
        json={"title": "Onboarding questions"},
        headers=_auth(token),
    )
    assert create_resp.status_code == 201
    assert create_resp.json()["title"] == "Onboarding questions"

    list_resp = await client.get(
        f"/api/v1/organizations/{org_id}/chat/conversations", headers=_auth(token)
    )
    assert len(list_resp.json()) == 1


async def test_chat_message_retrieves_relevant_chunks_and_cites_them(client):
    token = await _register_and_login(client, "chatuser2@example.com")
    org_id = await _create_org(client, token)

    await _upload_document(
        client, token, org_id, "vacation_policy.txt",
        b"Employees are entitled to 20 days of paid vacation per year. " * 20,
    )
    await _upload_document(
        client, token, org_id, "server_specs.txt",
        b"The data center servers require ambient temperature below 22 degrees Celsius. " * 20,
    )

    conv_resp = await client.post(
        f"/api/v1/organizations/{org_id}/chat/conversations", json={}, headers=_auth(token)
    )
    conversation_id = conv_resp.json()["id"]

    message_resp = await client.post(
        f"/api/v1/organizations/{org_id}/chat/conversations/{conversation_id}/messages",
        json={"content": "How many vacation days do employees get?"},
        headers=_auth(token),
    )
    assert message_resp.status_code == 201
    body = message_resp.json()
    assert body["role"] == "assistant"
    assert body["content"]  # FakeLLMProvider always returns non-empty text
    assert len(body["citations"]) > 0
    # The vacation policy document should be cited over the unrelated server spec doc.
    cited_filenames = {c["filename"] for c in body["citations"]}
    assert "vacation_policy.txt" in cited_filenames


async def test_conversation_scoped_to_single_document_only_retrieves_from_it(client):
    token = await _register_and_login(client, "chatuser3@example.com")
    org_id = await _create_org(client, token)

    doc_a_id = await _upload_document(
        client, token, org_id, "doc_a.txt", b"Doc A discusses the refund policy in detail. " * 20
    )
    await _upload_document(
        client, token, org_id, "doc_b.txt", b"Doc B discusses the refund policy in detail too. " * 20
    )

    conv_resp = await client.post(
        f"/api/v1/organizations/{org_id}/chat/conversations",
        json={"document_id": doc_a_id},
        headers=_auth(token),
    )
    conversation_id = conv_resp.json()["id"]

    message_resp = await client.post(
        f"/api/v1/organizations/{org_id}/chat/conversations/{conversation_id}/messages",
        json={"content": "What is the refund policy?"},
        headers=_auth(token),
    )
    citations = message_resp.json()["citations"]
    assert all(c["document_id"] == doc_a_id for c in citations)


async def test_message_history_is_persisted_as_memory(client):
    token = await _register_and_login(client, "chatuser4@example.com")
    org_id = await _create_org(client, token)
    await _upload_document(client, token, org_id, "notes.txt", b"Some general notes. " * 20)

    conv_resp = await client.post(
        f"/api/v1/organizations/{org_id}/chat/conversations", json={}, headers=_auth(token)
    )
    conversation_id = conv_resp.json()["id"]

    await client.post(
        f"/api/v1/organizations/{org_id}/chat/conversations/{conversation_id}/messages",
        json={"content": "First question"},
        headers=_auth(token),
    )
    await client.post(
        f"/api/v1/organizations/{org_id}/chat/conversations/{conversation_id}/messages",
        json={"content": "Second question"},
        headers=_auth(token),
    )

    messages_resp = await client.get(
        f"/api/v1/organizations/{org_id}/chat/conversations/{conversation_id}/messages",
        headers=_auth(token),
    )
    messages = messages_resp.json()
    # 2 user + 2 assistant messages, in order.
    assert len(messages) == 4
    assert [m["role"] for m in messages] == ["user", "assistant", "user", "assistant"]
    assert messages[0]["content"] == "First question"
    assert messages[2]["content"] == "Second question"


async def test_chat_is_scoped_to_organization(client):
    token_a = await _register_and_login(client, "chatorga@example.com")
    token_b = await _register_and_login(client, "chatorgb@example.com")
    org_a = await _create_org(client, token_a, "Org A")
    org_b = await _create_org(client, token_b, "Org B")

    await client.post(
        f"/api/v1/organizations/{org_a}/chat/conversations", json={}, headers=_auth(token_a)
    )

    list_resp_b = await client.get(
        f"/api/v1/organizations/{org_b}/chat/conversations", headers=_auth(token_b)
    )
    assert list_resp_b.json() == []


async def test_non_member_cannot_access_conversations(client):
    owner_token = await _register_and_login(client, "chatowner5@example.com")
    outsider_token = await _register_and_login(client, "chatoutsider5@example.com")
    org_id = await _create_org(client, owner_token)

    resp = await client.get(
        f"/api/v1/organizations/{org_id}/chat/conversations", headers=_auth(outsider_token)
    )
    assert resp.status_code == 403


async def test_message_to_nonexistent_conversation_404s(client):
    token = await _register_and_login(client, "chatuser6@example.com")
    org_id = await _create_org(client, token)
    import uuid

    fake_id = uuid.uuid4()
    resp = await client.post(
        f"/api/v1/organizations/{org_id}/chat/conversations/{fake_id}/messages",
        json={"content": "Hello?"},
        headers=_auth(token),
    )
    assert resp.status_code == 404
