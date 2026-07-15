import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict


class AuditLogRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    organization_id: uuid.UUID | None
    user_id: uuid.UUID | None
    event_type: str
    resource_type: str | None
    resource_id: str | None
    method: str | None
    path: str | None
    status_code: int | None
    ip_address: str | None
    latency_ms: int | None
    event_metadata: dict
    created_at: datetime
