"""
Document domain models.

`Document` is the stable identity a user refers to ("the Q3 handbook").
`DocumentVersion` is an immutable snapshot of a specific upload — its own
storage key, checksum, and processing status — so re-uploading never
mutates history. `DocumentChunk` rows belong to exactly one version, which
is what lets a later AI citation point at the precise version it was
generated from even after the document changes.
"""
import uuid
from enum import Enum

from sqlalchemy import BigInteger, ForeignKey, Integer, JSON, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.core.models_mixins import SoftDeleteMixin, TimestampMixin, UUIDPrimaryKeyMixin


class DocumentStatus(str, Enum):
    PENDING = "pending"       # uploaded, awaiting processing
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"
    NEEDS_OCR = "needs_ocr"    # extracted zero text; likely a scanned PDF


class Document(Base, UUIDPrimaryKeyMixin, TimestampMixin, SoftDeleteMixin):
    __tablename__ = "documents"

    organization_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("organizations.id"), nullable=False, index=True
    )
    uploaded_by_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("users.id"), nullable=False
    )
    filename: Mapped[str] = mapped_column(String(500), nullable=False)
    content_type: Mapped[str] = mapped_column(String(255), nullable=False)
    latest_version_number: Mapped[int] = mapped_column(Integer, default=1, nullable=False)

    versions: Mapped[list["DocumentVersion"]] = relationship(
        back_populates="document",
        cascade="all, delete-orphan",
        order_by="DocumentVersion.version_number",
    )

    def __repr__(self) -> str:
        return f"<Document id={self.id} filename={self.filename}>"


class DocumentVersion(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "document_versions"
    __table_args__ = (
        UniqueConstraint("document_id", "version_number", name="uq_document_version"),
    )

    document_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("documents.id"), nullable=False, index=True
    )
    version_number: Mapped[int] = mapped_column(Integer, nullable=False)
    storage_key: Mapped[str] = mapped_column(String(1000), nullable=False)
    size_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)
    checksum_sha256: Mapped[str] = mapped_column(String(64), nullable=False)

    status: Mapped[str] = mapped_column(
        String(50), default=DocumentStatus.PENDING.value, nullable=False
    )
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    page_count: Mapped[int | None] = mapped_column(Integer, nullable=True)

    document: Mapped["Document"] = relationship(back_populates="versions")
    chunks: Mapped[list["DocumentChunk"]] = relationship(
        back_populates="version",
        cascade="all, delete-orphan",
        order_by="DocumentChunk.chunk_index",
    )


class DocumentChunk(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "document_chunks"
    __table_args__ = (
        UniqueConstraint("document_version_id", "chunk_index", name="uq_chunk_order"),
    )

    document_version_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("document_versions.id"), nullable=False, index=True
    )
    chunk_index: Mapped[int] = mapped_column(Integer, nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    token_count: Mapped[int] = mapped_column(Integer, nullable=False)

    # Populated in Milestone 3 (embeddings). Nullable now so this table
    # doesn't need a migration rewrite once embeddings land — only an
    # ALTER to add the vector column, handled there. Using generic JSON
    # (not Postgres JSONB) keeps this portable for the SQLite test suite;
    # production can move to JSONB/pgvector in the Milestone 3 migration.
    embedding: Mapped[list[float] | None] = mapped_column(JSON, nullable=True)

    chunk_metadata: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)

    version: Mapped["DocumentVersion"] = relationship(back_populates="chunks")
