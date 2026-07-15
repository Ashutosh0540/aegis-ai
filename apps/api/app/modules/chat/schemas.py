import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class ConversationCreate(BaseModel):
    title: str | None = None
    document_id: uuid.UUID | None = None


class ConversationRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    organization_id: uuid.UUID
    created_by_id: uuid.UUID
    title: str | None
    document_id: uuid.UUID | None
    created_at: datetime


class CitationRead(BaseModel):
    chunk_id: str
    document_id: str
    document_version_id: str
    chunk_index: int
    filename: str
    score: float


class ChatMessageRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    conversation_id: uuid.UUID
    role: str
    content: str
    citations: list[CitationRead]
    created_at: datetime


class ChatMessageCreate(BaseModel):
    content: str = Field(min_length=1, max_length=8000)
