"""HTTP routes for /api/v1/users. Thin — delegates to service.py."""
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.deps import get_current_active_user
from app.modules.users.models import User
from app.modules.users.schemas import UserRead, UserUpdate
from app.modules.users.service import update_user

router = APIRouter(prefix="/users", tags=["users"])


@router.get("/me", response_model=UserRead)
async def read_current_user(current_user: User = Depends(get_current_active_user)):
    return current_user


@router.patch("/me", response_model=UserRead)
async def update_current_user(
    payload: UserUpdate,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    return await update_user(db, current_user, payload)
