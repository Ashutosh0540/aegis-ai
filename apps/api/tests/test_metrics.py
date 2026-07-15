import pytest

pytestmark = pytest.mark.asyncio


async def test_metrics_endpoint_returns_prometheus_text_format(client):
    resp = await client.get("/metrics")
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("text/plain")
    assert "http_requests_total" in resp.text
    assert "http_request_duration_seconds" in resp.text


async def test_requests_increment_the_counter(client):
    before = await client.get("/metrics")
    await client.post(
        "/api/v1/auth/register",
        json={
            "email": "metricsuser@example.com",
            "password": "supersecret1",
            "full_name": "Metrics User",
        },
    )
    after = await client.get("/metrics")

    def _count(body: str) -> float:
        total = 0.0
        for line in body.splitlines():
            if line.startswith("http_requests_total{") and 'path="/api/v1/auth/register"' in line:
                total += float(line.rsplit(" ", 1)[-1])
        return total

    assert _count(after.text) > _count(before.text)


async def test_metrics_path_label_uses_route_template_not_raw_ids(client):
    """Guards against cardinality blowups: a UUID in the URL should collapse
    to the route's `{org_id}`-style template in the exported label, not
    appear as a literal UUID."""
    import uuid

    org_id = str(uuid.uuid4())
    await client.get(f"/api/v1/organizations/{org_id}/tickets")
    resp = await client.get("/metrics")
    assert "/organizations/{org_id}/tickets" in resp.text
    assert org_id not in resp.text


async def test_metrics_endpoint_itself_is_not_counted(client):
    """/metrics is in _SKIP_PATHS so scraping it doesn't inflate its own
    counters on every scrape."""
    resp = await client.get("/metrics")
    assert 'path="/metrics"' not in resp.text
