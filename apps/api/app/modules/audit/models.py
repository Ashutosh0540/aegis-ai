"""
AuditLog domain model.

Deliberately append-only (no soft delete, no update path) — an audit log
that could be edited or hidden defeats its own purpose. Covers all three
categories the spec calls for: every AI action (agent_name populated),
every API request (via the middleware in app.core.audit_middleware), and
security events (event_type like "auth.login_failed").

`organization_id` and `user_id` are nullable because some events precede
having either (e.g. a failed login attempt for an email that isn't
registered, or a request to a public endpoint).
"""
import uuid

from sqlalchemy import ForeignKey, Integer, JSON, String
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.core.models_mixins import TimestampMixin, UUIDPrimaryKeyMixin


class AuditLog(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "audit_logs"

    organization_id: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("organizations.id"), nullable=True, index=True
    )
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("users.id"), nullable=True, index=True
    )

    # e.g. "api_request", "auth.login_failed", "auth.login_succeeded",
    # "agent.invoked", "document.uploaded", "ticket.created"
    event_type: Mapped[str] = mapped_column(String(100), nullable=False, index=True)

    resource_type: Mapped[str | None] = mapped_column(String(100), nullable=True)
    resource_id: Mapped[str | None] = mapped_column(String(100), nullable=True)

    method: Mapped[str | None] = mapped_column(String(10), nullable=True)
    path: Mapped[str | None] = mapped_column(String(500), nullable=True)
    status_code: Mapped[int | None] = mapped_column(Integer, nullable=True)
    ip_address: Mapped[str | None] = mapped_column(String(64), nullable=True)
    latency_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)

    event_metadata: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
