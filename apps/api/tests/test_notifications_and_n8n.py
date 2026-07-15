import logging

from app.core.n8n_client import FakeN8nClient, HttpN8nClient
from app.core.notifications import ConsoleEmailProvider, FakeEmailProvider


def test_fake_email_provider_records_sends():
    provider = FakeEmailProvider()
    provider.send_email(to="a@example.com", subject="Hi", body="Hello there")
    assert len(provider.sent_emails) == 1
    assert provider.sent_emails[0]["to"] == "a@example.com"
    assert provider.sent_emails[0]["subject"] == "Hi"


def test_console_email_provider_logs_instead_of_sending(caplog):
    provider = ConsoleEmailProvider()
    with caplog.at_level(logging.INFO):
        provider.send_email(to="b@example.com", subject="Test Subject", body="Body text")
    assert "b@example.com" in caplog.text
    assert "Test Subject" in caplog.text


def test_fake_n8n_client_records_triggered_webhooks():
    client = FakeN8nClient()
    result = client.trigger_webhook("ticket.created", {"ticket_id": "abc123"})
    assert result is True
    assert len(client.triggered) == 1
    assert client.triggered[0]["event"] == "ticket.created"
    assert client.triggered[0]["payload"]["ticket_id"] == "abc123"


def test_http_n8n_client_returns_false_on_unreachable_host():
    # Real HttpN8nClient against an address nothing is listening on — this
    # genuinely exercises the error-handling path without needing a real
    # n8n instance.
    client = HttpN8nClient("http://localhost:1", timeout_seconds=1.0)
    result = client.trigger_webhook("ticket.created", {"foo": "bar"})
    assert result is False
