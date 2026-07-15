"""
Chat domain models.

`Conversation` groups a sequence of messages (the "memory" the RAG prompt
draws recent history from). `ChatMessage.citations` stores exactly which
chunks (by id, document, and version) informed an assistant reply — this
is what lets the frontend render "Source: employee_handbook.pdf, v2"
under an answer rather than just trusting the LLM's prose.
"""
import uuid
from enum import Enum

from sqlalchemy import ForeignKey, JSON, String, Text
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.core.models_mixins import SoftDeleteMixin, TimestampMixin, UUIDPrimaryKeyMixin


class MessageRole(str, Enum):
    USER = "user"
    ASSISTANT = "assistant"


class Conversation(Base, UUIDPrimaryKeyMixin, TimestampMixin, SoftDeleteMixin):
    __tablename__ = "conversations"

    organization_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("organizations.id"), nullable=False, index=True
    )
    created_by_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("users.id"), nullable=False
    )
    title: Mapped[str | None] = mapped_column(String(255), nullable=True)

    # Optional scope: if set, retrieval is restricted to this document only.
    document_id: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("documents.id"), nullable=True
    )

    messages: Mapped[list["ChatMessage"]] = relationship(
        back_populates="conversation",
        cascade="all, delete-orphan",
        order_by="ChatMessage.created_at",
    )


class ChatMessage(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "chat_messages"

    conversation_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("conversations.id"), nullable=False, index=True
    )
    role: Mapped[str] = mapped_column(String(20), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)

    # List of {"chunk_id", "document_id", "document_version_id",
    # "chunk_index", "filename", "score"} — empty for user messages.
    citations: Mapped[list] = mapped_column(JSON, default=list, nullable=False)

    conversation: Mapped["Conversation"] = relationship(back_populates="messages")
