"""
Ticket domain model — the concrete "ticket creation" feature from the
spec. Creating a ticket fires an n8n webhook (see service.py); what
happens next (Slack notification, assignment, escalation) is n8n's job,
configured externally — this app's responsibility ends at emitting the
event.
"""
import uuid
from enum import Enum

from sqlalchemy import ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.core.models_mixins import SoftDeleteMixin, TimestampMixin, UUIDPrimaryKeyMixin


class TicketStatus(str, Enum):
    OPEN = "open"
    IN_PROGRESS = "in_progress"
    RESOLVED = "resolved"
    CLOSED = "closed"


class TicketPriority(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    URGENT = "urgent"


class TicketSource(str, Enum):
    MANUAL = "manual"     # created directly via the API/UI
    AGENT = "agent"        # created by the Workflow Agent from a chat/agent request


class Ticket(Base, UUIDPrimaryKeyMixin, TimestampMixin, SoftDeleteMixin):
    __tablename__ = "tickets"

    organization_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("organizations.id"), nullable=False, index=True
    )
    created_by_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("users.id"), nullable=False
    )
    assigned_to_id: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("users.id"), nullable=True
    )

    title: Mapped[str] = mapped_column(String(500), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(20), default=TicketStatus.OPEN.value, nullable=False)
    priority: Mapped[str] = mapped_column(
        String(20), default=TicketPriority.MEDIUM.value, nullable=False
    )
    source: Mapped[str] = mapped_column(String(20), default=TicketSource.MANUAL.value, nullable=False)
