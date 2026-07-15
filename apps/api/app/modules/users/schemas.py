"""Wire-level contracts for the users module. Never expose ORM models directly."""
import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr


class UserRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    email: EmailStr
    full_name: str
    is_active: bool
    is_email_verified: bool
    created_at: datetime


class UserUpdate(BaseModel):
    full_name: str | None = None
