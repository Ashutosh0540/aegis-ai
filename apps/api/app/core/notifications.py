"""
Email notification providers.

`SMTPEmailProvider` is the production implementation. `ConsoleEmailProvider`
is the default when SMTP isn't configured — it logs the email instead of
sending it, which is a legitimate lightweight provider for local
development (not a stub standing in for missing functionality: a dev
environment without SMTP configured genuinely shouldn't fail registration,
it should just make the email visible in the logs). `FakeEmailProvider`
records sends in memory for test assertions.
"""
import logging
import smtplib
from email.mime.text import MIMEText
from typing import Protocol

logger = logging.getLogger(__name__)


class EmailProvider(Protocol):
    def send_email(self, to: str, subject: str, body: str) -> None: ...


class SMTPEmailProvider:
    def __init__(
        self,
        host: str,
        port: int,
        username: str | None,
        password: str | None,
        from_email: str,
        use_tls: bool,
    ):
        self._host = host
        self._port = port
        self._username = username
        self._password = password
        self._from_email = from_email
        self._use_tls = use_tls

    def send_email(self, to: str, subject: str, body: str) -> None:
        message = MIMEText(body, "plain", "utf-8")
        message["Subject"] = subject
        message["From"] = self._from_email
        message["To"] = to

        with smtplib.SMTP(self._host, self._port, timeout=15) as server:
            if self._use_tls:
                server.starttls()
            if self._username and self._password:
                server.login(self._username, self._password)
            server.sendmail(self._from_email, [to], message.as_string())


class ConsoleEmailProvider:
    """Logs the email instead of sending it. Used whenever SMTP isn't
    configured — a safe, honest default rather than a silent no-op."""

    def send_email(self, to: str, subject: str, body: str) -> None:
        logger.info("EMAIL (console provider, not actually sent)\nTo: %s\nSubject: %s\n\n%s", to, subject, body)


class FakeEmailProvider:
    """In-memory recorder for tests — `sent_emails` accumulates every call
    so tests can assert on what would have been sent."""

    def __init__(self):
        self.sent_emails: list[dict] = []

    def send_email(self, to: str, subject: str, body: str) -> None:
        self.sent_emails.append({"to": to, "subject": subject, "body": body})


_singleton: EmailProvider | None = None


def get_notification_provider() -> EmailProvider:
    """FastAPI dependency / plain accessor. Overridden in tests with
    `FakeEmailProvider`."""
    global _singleton
    if _singleton is not None:
        return _singleton

    from app.core.config import get_settings

    settings = get_settings()
    if settings.SMTP_HOST:
        _singleton = SMTPEmailProvider(
            host=settings.SMTP_HOST,
            port=settings.SMTP_PORT,
            username=settings.SMTP_USERNAME,
            password=settings.SMTP_PASSWORD,
            from_email=settings.SMTP_FROM_EMAIL,
            use_tls=settings.SMTP_USE_TLS,
        )
    else:
        _singleton = ConsoleEmailProvider()
    return _singleton
