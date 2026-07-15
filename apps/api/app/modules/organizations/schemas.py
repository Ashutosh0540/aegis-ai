import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field

from app.modules.organizations.models import OrgRole


class OrganizationCreate(BaseModel):
    name: str = Field(min_length=2, max_length=255)


class OrganizationRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    slug: str
    created_at: datetime


class OrganizationMemberRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    user_id: uuid.UUID
    organization_id: uuid.UUID
    role: str
    created_at: datetime


class InviteCreate(BaseModel):
    email: EmailStr
    role: OrgRole = OrgRole.MEMBER


class InviteAccept(BaseModel):
    token: str


class InviteRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    email: EmailStr
    role: str
    accepted: bool
    created_at: datetime
