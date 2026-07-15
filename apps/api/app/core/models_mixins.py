"""
Shared ORM mixins used across every module's models.

Keeping these in one place enforces the DB conventions mandated by the spec:
UUID primary keys, created_at/updated_at, and soft delete — without every
module re-implementing them slightly differently.
"""
import uuid
from datetime import datetime, timezone

from sqlalchemy import DateTime
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class UUIDPrimaryKeyMixin:
    """UUID v4 primary key, generated application-side."""

    id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )


class TimestampMixin:
    """created_at / updated_at, both server- and app-managed as UTC."""

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utcnow,
        onupdate=utcnow,
        nullable=False,
    )


class SoftDeleteMixin:
    """
    Soft delete flag + timestamp. Queries must explicitly filter
    `deleted_at.is_(None)` — enforced at the repository/service layer,
    not the DB layer, to keep this framework-agnostic.
    """

    deleted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, default=None
    )

    @property
    def is_deleted(self) -> bool:
        return self.deleted_at is not None
