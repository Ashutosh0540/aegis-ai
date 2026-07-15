"""
Shared FastAPI dependencies: current authenticated user, current
organization context, and role-based access control (RBAC) guards.

Every protected route in every module depends on these rather than
re-implementing token parsing, so auth behavior is identical platform-wide.
"""
import uuid

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.database import get_db
from app.core.security import TokenType, decode_token
from app.modules.organizations.models import OrganizationMember
from app.modules.users.models import User

settings = get_settings()

oauth2_scheme = OAuth2PasswordBearer(tokenUrl=f"{settings.API_V1_PREFIX}/auth/login")


async def get_current_user(
    token: str = Depends(oauth2_scheme),
    db: AsyncSession = Depends(get_db),
) -> User:
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = decode_token(token)
    except JWTError:
        raise credentials_exception

    if payload.get("type") != TokenType.ACCESS.value:
        raise credentials_exception

    user_id = payload.get("sub")
    if user_id is None:
        raise credentials_exception

    result = await db.execute(
        select(User).where(User.id == uuid.UUID(user_id), User.deleted_at.is_(None))
    )
    user = result.scalar_one_or_none()
    if user is None or not user.is_active:
        raise credentials_exception
    return user


async def get_current_active_user(
    current_user: User = Depends(get_current_user),
) -> User:
    if not current_user.is_active:
        raise HTTPException(status_code=400, detail="Inactive user")
    return current_user


class RequireOrgRole:
    """
    Dependency factory enforcing that the current user holds one of the
    given roles within the org referenced by the `org_id` path parameter.

    Usage:  Depends(RequireOrgRole("owner", "admin"))
    """

    def __init__(self, *allowed_roles: str):
        self.allowed_roles = set(allowed_roles)

    async def __call__(
        self,
        org_id: uuid.UUID,
        current_user: User = Depends(get_current_active_user),
        db: AsyncSession = Depends(get_db),
    ) -> OrganizationMember:
        result = await db.execute(
            select(OrganizationMember).where(
                OrganizationMember.organization_id == org_id,
                OrganizationMember.user_id == current_user.id,
                OrganizationMember.deleted_at.is_(None),
            )
        )
        membership = result.scalar_one_or_none()
        if membership is None:
            raise HTTPException(status_code=403, detail="Not a member of this organization")
        if self.allowed_roles and membership.role not in self.allowed_roles:
            raise HTTPException(status_code=403, detail="Insufficient organization role")
        return membership
