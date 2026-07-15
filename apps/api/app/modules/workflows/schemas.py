import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.modules.workflows.models import TicketPriority, TicketStatus


class TicketCreate(BaseModel):
    title: str = Field(min_length=1, max_length=500)
    description: str = Field(min_length=1, max_length=8000)
    priority: TicketPriority = TicketPriority.MEDIUM


class TicketUpdate(BaseModel):
    status: TicketStatus | None = None
    priority: TicketPriority | None = None
    assigned_to_id: uuid.UUID | None = None


class TicketRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    organization_id: uuid.UUID
    created_by_id: uuid.UUID
    assigned_to_id: uuid.UUID | None
    title: str
    description: str
    status: str
    priority: str
    source: str
    created_at: datetime
    updated_at: datetime
