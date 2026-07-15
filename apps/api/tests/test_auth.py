import pytest

pytestmark = pytest.mark.asyncio


async def test_register_creates_user(client):
    resp = await client.post(
        "/api/v1/auth/register",
        json={"email": "alice@example.com", "password": "supersecret1", "full_name": "Alice"},
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["email"] == "alice@example.com"
    assert body["is_email_verified"] is False
    assert "hashed_password" not in body  # never leak the hash


async def test_register_duplicate_email_rejected(client):
    payload = {"email": "bob@example.com", "password": "supersecret1", "full_name": "Bob"}
    first = await client.post("/api/v1/auth/register", json=payload)
    assert first.status_code == 201

    second = await client.post("/api/v1/auth/register", json=payload)
    assert second.status_code == 409


async def test_login_success_returns_token_pair(client):
    await client.post(
        "/api/v1/auth/register",
        json={"email": "carol@example.com", "password": "supersecret1", "full_name": "Carol"},
    )
    resp = await client.post(
        "/api/v1/auth/login",
        data={"username": "carol@example.com", "password": "supersecret1"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert "access_token" in body
    assert "refresh_token" in body
    assert body["token_type"] == "bearer"


async def test_login_wrong_password_rejected(client):
    await client.post(
        "/api/v1/auth/register",
        json={"email": "dave@example.com", "password": "correcthorse1", "full_name": "Dave"},
    )
    resp = await client.post(
        "/api/v1/auth/login",
        data={"username": "dave@example.com", "password": "wrongpassword"},
    )
    assert resp.status_code == 401


async def test_refresh_token_issues_new_access_token(client):
    await client.post(
        "/api/v1/auth/register",
        json={"email": "erin@example.com", "password": "supersecret1", "full_name": "Erin"},
    )
    login_resp = await client.post(
        "/api/v1/auth/login",
        data={"username": "erin@example.com", "password": "supersecret1"},
    )
    refresh_token = login_resp.json()["refresh_token"]

    refresh_resp = await client.post(
        "/api/v1/auth/refresh", json={"refresh_token": refresh_token}
    )
    assert refresh_resp.status_code == 200
    assert "access_token" in refresh_resp.json()


async def test_forgot_password_always_returns_202(client):
    resp = await client.post(
        "/api/v1/auth/forgot-password", json={"email": "nonexistent@example.com"}
    )
    # Must not reveal whether the account exists.
    assert resp.status_code == 202


async def test_register_sends_verification_email(client, fake_email_provider):
    await client.post(
        "/api/v1/auth/register",
        json={"email": "verifyme@example.com", "password": "supersecret1", "full_name": "Verify Me"},
    )
    sent = [e for e in fake_email_provider.sent_emails if e["to"] == "verifyme@example.com"]
    assert len(sent) == 1
    assert "verify" in sent[0]["subject"].lower()
    assert "token=" in sent[0]["body"]


async def test_forgot_password_sends_reset_email_for_existing_user(client, fake_email_provider):
    await client.post(
        "/api/v1/auth/register",
        json={"email": "resetme@example.com", "password": "supersecret1", "full_name": "Reset Me"},
    )
    fake_email_provider.sent_emails.clear()  # ignore the registration email

    await client.post("/api/v1/auth/forgot-password", json={"email": "resetme@example.com"})
    sent = [e for e in fake_email_provider.sent_emails if e["to"] == "resetme@example.com"]
    assert len(sent) == 1
    assert "reset" in sent[0]["subject"].lower()


async def test_forgot_password_sends_no_email_for_nonexistent_user(client, fake_email_provider):
    await client.post("/api/v1/auth/forgot-password", json={"email": "doesnotexist@example.com"})
    assert fake_email_provider.sent_emails == []
