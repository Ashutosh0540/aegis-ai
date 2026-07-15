import pytest

pytestmark = pytest.mark.asyncio


async def _register_and_login(client, email="frank@example.com"):
    await client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": "supersecret1", "full_name": "Frank"},
    )
    login_resp = await client.post(
        "/api/v1/auth/login", data={"username": email, "password": "supersecret1"}
    )
    return login_resp.json()["access_token"]


async def test_get_current_user_requires_auth(client):
    resp = await client.get("/api/v1/users/me")
    assert resp.status_code == 401


async def test_get_current_user_returns_profile(client):
    token = await _register_and_login(client)
    resp = await client.get(
        "/api/v1/users/me", headers={"Authorization": f"Bearer {token}"}
    )
    assert resp.status_code == 200
    assert resp.json()["email"] == "frank@example.com"


async def test_update_current_user_full_name(client):
    token = await _register_and_login(client)
    resp = await client.patch(
        "/api/v1/users/me",
        json={"full_name": "Franklin"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    assert resp.json()["full_name"] == "Franklin"
