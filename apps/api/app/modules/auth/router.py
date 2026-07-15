"""HTTP routes for /api/v1/auth."""
from fastapi import APIRouter, Depends, Request
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.ext.asyncio import AsyncSession
from slowapi import Limiter
from slowapi.util import get_remote_address

from app.core.database import get_db
from app.core.notifications import EmailProvider, get_notification_provider
from app.modules.auth import service
from app.modules.auth.schemas import (
    ForgotPasswordRequest,
    RefreshRequest,
    RegisterRequest,
    ResetPasswordRequest,
    TokenResponse,
    VerifyEmailRequest,
)
from app.modules.users.schemas import UserRead

router = APIRouter(prefix="/auth", tags=["auth"])
limiter = Limiter(key_func=get_remote_address)


@router.post("/register", response_model=UserRead, status_code=201)
async def register(
    payload: RegisterRequest,
    db: AsyncSession = Depends(get_db),
    notification_provider: EmailProvider = Depends(get_notification_provider),
):
    user, _verification_token = await service.register_user(db, payload, notification_provider)
    return user


@router.post("/login", response_model=TokenResponse)
@limiter.limit("10/minute")
async def login(
    request: Request,
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: AsyncSession = Depends(get_db),
):
    user = await service.authenticate_user(db, form_data.username, form_data.password)
    access, refresh = service.issue_token_pair(user)
    return TokenResponse(access_token=access, refresh_token=refresh)


@router.post("/refresh", response_model=TokenResponse)
async def refresh(payload: RefreshRequest, db: AsyncSession = Depends(get_db)):
    access, refresh_token = await service.refresh_access_token(db, payload.refresh_token)
    return TokenResponse(access_token=access, refresh_token=refresh_token)


@router.post("/verify-email", status_code=200)
async def verify_email(payload: VerifyEmailRequest, db: AsyncSession = Depends(get_db)):
    await service.verify_email(db, payload.token)
    return {"detail": "Email verified successfully"}


@router.post("/forgot-password", status_code=202)
@limiter.limit("5/minute")
async def forgot_password(
    request: Request,
    payload: ForgotPasswordRequest,
    db: AsyncSession = Depends(get_db),
    notification_provider: EmailProvider = Depends(get_notification_provider),
):
    await service.create_password_reset_token(db, payload.email, notification_provider)
    # Always return 202 regardless of whether the email exists, to avoid
    # leaking account existence.
    return {"detail": "If that email exists, a reset link has been sent"}


@router.post("/reset-password", status_code=200)
async def reset_password(payload: ResetPasswordRequest, db: AsyncSession = Depends(get_db)):
    await service.reset_password(db, payload.token, payload.new_password)
    return {"detail": "Password has been reset successfully"}
