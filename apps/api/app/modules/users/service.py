"""
Business logic for the users module. Framework-agnostic — takes a DB
session and plain values in, returns ORM objects or raises domain
exceptions. No FastAPI/HTTP concerns live here.
"""
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.users.models import User
from app.modules.users.schemas import UserUpdate


async def get_user_by_id(db: AsyncSession, user_id: uuid.UUID) -> User | None:
    result = await db.execute(
        select(User).where(User.id == user_id, User.deleted_at.is_(None))
    )
    return result.scalar_one_or_none()


async def get_user_by_email(db: AsyncSession, email: str) -> User | None:
    result = await db.execute(
        select(User).where(User.email == email.lower(), User.deleted_at.is_(None))
    )
    return result.scalar_one_or_none()


async def update_user(db: AsyncSession, user: User, payload: UserUpdate) -> User:
    if payload.full_name is not None:
        user.full_name = payload.full_name
    await db.commit()
    await db.refresh(user)
    return user
