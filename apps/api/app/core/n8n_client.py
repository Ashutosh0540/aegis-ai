"""
n8n workflow automation client.

The app's job is to emit events (a ticket was created, a document was
uploaded) — what happens as a result (Slack notification, round-robin
assignment, a follow-up email) is n8n's job, configured externally in the
n8n editor (see `workflows/n8n/` for example workflow definitions this
project ships with). This client is deliberately a thin, one-directional
fire-and-forget HTTP call: workflow automation failing should never break
the primary request that triggered it.
"""
import logging
from typing import Protocol

logger = logging.getLogger(__name__)


class N8nClient(Protocol):
    def trigger_webhook(self, event: str, payload: dict) -> bool: ...


class HttpN8nClient:
    def __init__(self, base_url: str, timeout_seconds: float = 10.0):
        self._base_url = base_url.rstrip("/")
        self._timeout = timeout_seconds

    def trigger_webhook(self, event: str, payload: dict) -> bool:
        """POST to `{base_url}/webhook/{event}`. Returns True on a 2xx
        response, False on any failure — never raises, since a workflow
        automation outage shouldn't fail the request that triggered it."""
        import httpx

        try:
            response = httpx.post(
                f"{self._base_url}/webhook/{event}", json=payload, timeout=self._timeout
            )
            response.raise_for_status()
            return True
        except httpx.HTTPError as exc:
            logger.warning("n8n webhook '%s' failed: %s", event, exc)
            return False


class FakeN8nClient:
    """In-memory recorder for tests — `triggered` accumulates every call."""

    def __init__(self):
        self.triggered: list[dict] = []

    def trigger_webhook(self, event: str, payload: dict) -> bool:
        self.triggered.append({"event": event, "payload": payload})
        return True


_singleton: N8nClient | None = None


def get_n8n_client() -> N8nClient:
    """FastAPI dependency / plain accessor. Overridden in tests with
    `FakeN8nClient`."""
    global _singleton
    if _singleton is None:
        from app.core.config import get_settings

        settings = get_settings()
        _singleton = HttpN8nClient(settings.N8N_BASE_URL, settings.N8N_WEBHOOK_TIMEOUT_SECONDS)
    return _singleton
