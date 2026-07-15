import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class AgentInfo(BaseModel):
    name: str
    description: str


class AgentInvokeRequest(BaseModel):
    input: str = Field(min_length=1, max_length=8000)
    document_id: uuid.UUID | None = None


class CitationRead(BaseModel):
    chunk_id: str
    document_id: str
    document_version_id: str
    chunk_index: int
    filename: str
    score: float


class AgentRunRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    organization_id: uuid.UUID
    requested_by_id: uuid.UUID
    agent_name: str
    route_taken: str
    input_text: str
    output_text: str | None
    citations: list[CitationRead]
    status: str
    error_message: str | None
    latency_ms: int
    created_at: datetime
