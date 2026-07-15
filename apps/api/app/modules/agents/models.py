"""
AgentRun domain model.

A lightweight record of each ad-hoc agent invocation (via the /agents
endpoints, as opposed to a chat message — chat turns already have their
own audit trail via ChatMessage). Deliberately minimal today: just enough
shape (which agent, what route was taken, latency, status) that
Milestone 6's audit log and analytics dashboard can build on it rather
than inventing a parallel table later.
"""
import uuid
from enum import Enum

from sqlalchemy import ForeignKey, Integer, JSON, String, Text
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.core.models_mixins import TimestampMixin, UUIDPrimaryKeyMixin


class AgentRunStatus(str, Enum):
    SUCCESS = "success"
    ERROR = "error"


class AgentRun(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "agent_runs"

    organization_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("organizations.id"), nullable=False, index=True
    )
    requested_by_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("users.id"), nullable=False
    )
    agent_name: Mapped[str] = mapped_column(String(100), nullable=False)  # e.g. "supervisor"
    route_taken: Mapped[str] = mapped_column(String(100), nullable=False)  # e.g. "knowledge_agent"
    input_text: Mapped[str] = mapped_column(Text, nullable=False)
    output_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    citations: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    latency_ms: Mapped[int] = mapped_column(Integer, nullable=False)
