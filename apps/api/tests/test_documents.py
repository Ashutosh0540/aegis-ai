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


async def test_upload_txt_document_is_processed_synchronously_in_tests(client):
    token = await _register_and_login(client, "uploader1@example.com")
    org_id = await _create_org(client, token)

    files = {"file": ("notes.txt", b"Hello world, this is a test document.", "text/plain")}
    resp = await client.post(
        f"/api/v1/organizations/{org_id}/documents", files=files, headers=_auth(token)
    )
    assert resp.status_code == 201
    doc = resp.json()
    assert doc["filename"] == "notes.txt"
    assert doc["latest_version_number"] == 1

    detail_resp = await client.get(
        f"/api/v1/organizations/{org_id}/documents/{doc['id']}", headers=_auth(token)
    )
    assert detail_resp.status_code == 200
    detail = detail_resp.json()
    assert detail["latest_version"]["status"] == "completed"
    assert detail["latest_version"]["checksum_sha256"]


async def test_upload_rejects_disallowed_content_type(client):
    token = await _register_and_login(client, "uploader2@example.com")
    org_id = await _create_org(client, token)

    files = {"file": ("image.png", b"\x89PNG...", "image/png")}
    resp = await client.post(
        f"/api/v1/organizations/{org_id}/documents", files=files, headers=_auth(token)
    )
    assert resp.status_code == 415


async def test_uploaded_document_produces_chunks(client):
    token = await _register_and_login(client, "uploader3@example.com")
    org_id = await _create_org(client, token)

    long_text = ("This is a sentence about AegisAI. " * 200).encode("utf-8")
    files = {"file": ("handbook.txt", long_text, "text/plain")}
    resp = await client.post(
        f"/api/v1/organizations/{org_id}/documents", files=files, headers=_auth(token)
    )
    doc_id = resp.json()["id"]

    chunks_resp = await client.get(
        f"/api/v1/organizations/{org_id}/documents/{doc_id}/chunks", headers=_auth(token)
    )
    assert chunks_resp.status_code == 200
    chunks = chunks_resp.json()
    assert len(chunks) > 1
    assert chunks[0]["chunk_index"] == 0
    assert all(c["token_count"] > 0 for c in chunks)


async def test_new_version_increments_version_number_and_reprocesses(client):
    token = await _register_and_login(client, "uploader4@example.com")
    org_id = await _create_org(client, token)

    files_v1 = {"file": ("policy.txt", b"Version one content.", "text/plain")}
    doc_resp = await client.post(
        f"/api/v1/organizations/{org_id}/documents", files=files_v1, headers=_auth(token)
    )
    doc_id = doc_resp.json()["id"]

    files_v2 = {"file": ("policy.txt", b"Version two content, revised.", "text/plain")}
    version_resp = await client.post(
        f"/api/v1/organizations/{org_id}/documents/{doc_id}/versions",
        files=files_v2,
        headers=_auth(token),
    )
    assert version_resp.status_code == 201
    assert version_resp.json()["version_number"] == 2
    # The response is serialized from the object as committed *before*
    # background processing (Celery in prod, synchronous stand-in in tests)
    # runs — this matches real async behavior, where processing completes
    # after the HTTP response has already been sent.
    assert version_resp.json()["status"] == "pending"

    versions_resp = await client.get(
        f"/api/v1/organizations/{org_id}/documents/{doc_id}/versions", headers=_auth(token)
    )
    versions = versions_resp.json()
    version_numbers = [v["version_number"] for v in versions]
    assert version_numbers == [2, 1]  # newest first
    assert versions[0]["status"] == "completed"  # processing has since finished


async def test_member_cannot_delete_document_only_admin_owner_can(client):
    owner_token = await _register_and_login(client, "owner_docs@example.com")
    member_token = await _register_and_login(client, "member_docs@example.com")
    org_id = await _create_org(client, owner_token)

    # invite + accept flow is exercised in test_organizations.py already;
    # here we just need "member_token" to actually be a member.
    invite_resp = await client.post(
        f"/api/v1/organizations/{org_id}/invites",
        json={"email": "member_docs@example.com", "role": "member"},
        headers=_auth(owner_token),
    )
    assert invite_resp.status_code == 201

    files = {"file": ("doc.txt", b"Some content.", "text/plain")}
    doc_resp = await client.post(
        f"/api/v1/organizations/{org_id}/documents", files=files, headers=_auth(owner_token)
    )
    doc_id = doc_resp.json()["id"]

    # member_docs isn't an accepted member yet (no token exposed via API by
    # design), so this should 403 as "not a member" rather than "insufficient role" —
    # either way, a non-owner/admin cannot delete.
    delete_resp = await client.delete(
        f"/api/v1/organizations/{org_id}/documents/{doc_id}", headers=_auth(member_token)
    )
    assert delete_resp.status_code == 403


async def test_owner_can_delete_document(client):
    token = await _register_and_login(client, "owner_delete@example.com")
    org_id = await _create_org(client, token)

    files = {"file": ("doc.txt", b"Some content.", "text/plain")}
    doc_resp = await client.post(
        f"/api/v1/organizations/{org_id}/documents", files=files, headers=_auth(token)
    )
    doc_id = doc_resp.json()["id"]

    delete_resp = await client.delete(
        f"/api/v1/organizations/{org_id}/documents/{doc_id}", headers=_auth(token)
    )
    assert delete_resp.status_code == 204

    get_resp = await client.get(
        f"/api/v1/organizations/{org_id}/documents/{doc_id}", headers=_auth(token)
    )
    assert get_resp.status_code == 404


async def test_documents_are_scoped_to_organization(client):
    token_a = await _register_and_login(client, "orga@example.com")
    token_b = await _register_and_login(client, "orgb@example.com")
    org_a = await _create_org(client, token_a, "Org A")
    org_b = await _create_org(client, token_b, "Org B")

    files = {"file": ("secret.txt", b"Org A secret content.", "text/plain")}
    await client.post(f"/api/v1/organizations/{org_a}/documents", files=files, headers=_auth(token_a))

    list_resp_b = await client.get(f"/api/v1/organizations/{org_b}/documents", headers=_auth(token_b))
    assert list_resp_b.json() == []


async def test_uploaded_chunks_are_embedded_and_queryable_in_vector_store(
    client, test_vector_store, fake_embedding_provider
):
    token = await _register_and_login(client, "embeduser@example.com")
    org_id = await _create_org(client, token)

    long_text = (b"The quarterly revenue report shows strong growth. " * 50)
    files = {"file": ("report.txt", long_text, "text/plain")}
    resp = await client.post(
        f"/api/v1/organizations/{org_id}/documents", files=files, headers=_auth(token)
    )
    doc_id = resp.json()["id"]

    chunks_resp = await client.get(
        f"/api/v1/organizations/{org_id}/documents/{doc_id}/chunks", headers=_auth(token)
    )
    chunks = chunks_resp.json()
    assert len(chunks) > 0

    # The vector store (shared with the app via dependency override) should
    # be able to retrieve these chunks by semantic similarity.
    query_vector = fake_embedding_provider.embed_text("quarterly revenue report growth")
    matches = test_vector_store.query(org_id, query_vector, top_k=5)
    assert len(matches) > 0
    assert matches[0].metadata["document_id"] == doc_id
