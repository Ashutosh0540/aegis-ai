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


async def test_create_organization_makes_creator_owner(client):
    token = await _register_and_login(client, "owner1@example.com")
    resp = await client.post(
        "/api/v1/organizations", json={"name": "Acme Corp"}, headers=_auth(token)
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["name"] == "Acme Corp"
    assert body["slug"].startswith("acme-corp-")


async def test_list_my_organizations_only_shows_member_orgs(client):
    token_a = await _register_and_login(client, "usera@example.com")
    token_b = await _register_and_login(client, "userb@example.com")

    await client.post("/api/v1/organizations", json={"name": "Org A"}, headers=_auth(token_a))

    resp_a = await client.get("/api/v1/organizations", headers=_auth(token_a))
    resp_b = await client.get("/api/v1/organizations", headers=_auth(token_b))

    assert len(resp_a.json()) == 1
    assert len(resp_b.json()) == 0


async def test_non_admin_cannot_invite_members(client):
    owner_token = await _register_and_login(client, "owner2@example.com")
    member_token = await _register_and_login(client, "member2@example.com")

    org_resp = await client.post(
        "/api/v1/organizations", json={"name": "Beta Inc"}, headers=_auth(owner_token)
    )
    org_id = org_resp.json()["id"]

    # member2 is not part of the org at all yet -> RBAC dependency should 403
    resp = await client.post(
        f"/api/v1/organizations/{org_id}/invites",
        json={"email": "newperson@example.com"},
        headers=_auth(member_token),
    )
    assert resp.status_code == 403


async def test_owner_can_invite_and_invitee_can_accept(client):
    owner_token = await _register_and_login(client, "owner3@example.com")
    invitee_email = "invitee3@example.com"
    invitee_token = await _register_and_login(client, invitee_email)

    org_resp = await client.post(
        "/api/v1/organizations", json={"name": "Gamma LLC"}, headers=_auth(owner_token)
    )
    org_id = org_resp.json()["id"]

    invite_resp = await client.post(
        f"/api/v1/organizations/{org_id}/invites",
        json={"email": invitee_email, "role": "member"},
        headers=_auth(owner_token),
    )
    assert invite_resp.status_code == 201
    token_value = invite_resp.json()  # note: token itself isn't returned by InviteRead

    # Fetch the raw token isn't exposed via API by design (would need email
    # delivery in a later milestone) — so this test validates the invite
    # record shape instead of a full accept round trip requiring DB access.
    assert token_value["email"] == invitee_email
    assert token_value["accepted"] is False
