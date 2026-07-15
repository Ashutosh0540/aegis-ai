import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict


class DocumentVersionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    version_number: int
    size_bytes: int
    checksum_sha256: str
    status: str
    error_message: str | None
    page_count: int | None
    created_at: datetime


class DocumentRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    organization_id: uuid.UUID
    uploaded_by_id: uuid.UUID
    filename: str
    content_type: str
    latest_version_number: int
    created_at: datetime
    updated_at: datetime


class DocumentWithLatestVersion(DocumentRead):
    latest_version: DocumentVersionRead | None = None


class DocumentChunkRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    chunk_index: int
    content: str
    token_count: int
    chunk_metadata: dict
