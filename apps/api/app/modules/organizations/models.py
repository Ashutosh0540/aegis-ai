"""
Organization domain models.

An Organization is the tenant boundary. Every future module (documents,
chat, agents, workflows) will scope its rows by organization_id. Membership
is a separate join-table model (not a plain array column) so we can attach
role, invited_by, joined_at, and later per-member permission overrides.
"""
import uuid
from enum import Enum

from sqlalchemy import ForeignKey, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.core.models_mixins import SoftDeleteMixin, TimestampMixin, UUIDPrimaryKeyMixin


class OrgRole(str, Enum):
    OWNER = "owner"
    ADMIN = "admin"
    MEMBER = "member"


class Organization(Base, UUIDPrimaryKeyMixin, TimestampMixin, SoftDeleteMixin):
    __tablename__ = "organizations"

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    slug: Mapped[str] = mapped_column(String(255), unique=True, index=True, nullable=False)

    members: Mapped[list["OrganizationMember"]] = relationship(
        back_populates="organization", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<Organization id={self.id} slug={self.slug}>"


class OrganizationMember(Base, UUIDPrimaryKeyMixin, TimestampMixin, SoftDeleteMixin):
    __tablename__ = "organization_members"
    __table_args__ = (
        UniqueConstraint("organization_id", "user_id", name="uq_org_member"),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("organizations.id"), nullable=False, index=True
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("users.id"), nullable=False, index=True
    )
    role: Mapped[str] = mapped_column(String(50), default=OrgRole.MEMBER.value, nullable=False)

    organization: Mapped["Organization"] = relationship(back_populates="members")


class OrganizationInvite(Base, UUIDPrimaryKeyMixin, TimestampMixin, SoftDeleteMixin):
    """A pending invitation to join an organization by email."""

    __tablename__ = "organization_invites"
    __table_args__ = (
        UniqueConstraint("organization_id", "email", name="uq_org_invite"),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("organizations.id"), nullable=False, index=True
    )
    email: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[str] = mapped_column(String(50), default=OrgRole.MEMBER.value, nullable=False)
    token: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    accepted: Mapped[bool] = mapped_column(default=False, nullable=False)
