"""
Business logic for authentication: registration, login, token refresh,
email verification, and password reset.

Email delivery (verification + reset links) is now wired via the injected
`EmailProvider` (Milestone 5) — this closes out the TODOs left in
Milestone 1, when the notification module didn't exist yet.
"""
import secrets
import uuid
from datetime import datetime, timedelta, timezone

from fastapi import HTTPException, status
from jose import JWTError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.notifications import EmailProvider
from app.core.security import TokenType, create_token, decode_token, hash_password, verify_password
from app.modules.auth.models import AuthToken, AuthTokenPurpose
from app.modules.auth.schemas import RegisterRequest
from app.modules.users.models import User

settings = get_settings()

VERIFICATION_TOKEN_TTL_HOURS = 24
RESET_TOKEN_TTL_HOURS = 1


async def register_user(
    db: AsyncSession, payload: RegisterRequest, notification_provider: EmailProvider
) -> tuple[User, AuthToken]:
    existing = await db.execute(select(User).where(User.email == payload.email.lower()))
    if existing.scalar_one_or_none() is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="Email is already registered"
        )

    user = User(
        email=payload.email.lower(),
        hashed_password=hash_password(payload.password),
        full_name=payload.full_name,
        is_email_verified=False,
    )
    db.add(user)
    await db.flush()

    verification_token = AuthToken(
        user_id=user.id,
        token=secrets.token_urlsafe(32),
        purpose=AuthTokenPurpose.EMAIL_VERIFICATION.value,
        expires_at=datetime.now(timezone.utc) + timedelta(hours=VERIFICATION_TOKEN_TTL_HOURS),
    )
    db.add(verification_token)
    await db.commit()
    await db.refresh(user)
    await db.refresh(verification_token)

    verify_url = f"{settings.FRONTEND_BASE_URL}/verify-email?token={verification_token.token}"
    notification_provider.send_email(
        to=user.email,
        subject="Verify your AegisAI account",
        body=f"Welcome to AegisAI, {user.full_name}.\n\nVerify your email: {verify_url}\n\nThis link expires in {VERIFICATION_TOKEN_TTL_HOURS} hours.",
    )

    return user, verification_token


async def authenticate_user(db: AsyncSession, email: str, password: str) -> User:
    from app.modules.audit.service import record_event

    result = await db.execute(
        select(User).where(User.email == email.lower(), User.deleted_at.is_(None))
    )
    user = result.scalar_one_or_none()
    if user is None or user.hashed_password is None:
        await record_event(
            db, "auth.login_failed", event_metadata={"email": email.lower(), "reason": "no_such_user"}
        )
        raise HTTPException(status_code=401, detail="Incorrect email or password")
    if not verify_password(password, user.hashed_password):
        await record_event(
            db, "auth.login_failed", user_id=user.id, event_metadata={"reason": "bad_password"}
        )
        raise HTTPException(status_code=401, detail="Incorrect email or password")
    if not user.is_active:
        await record_event(db, "auth.login_failed", user_id=user.id, event_metadata={"reason": "inactive"})
        raise HTTPException(status_code=403, detail="Account is deactivated")

    await record_event(db, "auth.login_succeeded", user_id=user.id)
    return user


def issue_token_pair(user: User) -> tuple[str, str]:
    access = create_token(user.id, TokenType.ACCESS)
    refresh = create_token(user.id, TokenType.REFRESH)
    return access, refresh


async def refresh_access_token(db: AsyncSession, refresh_token: str) -> tuple[str, str]:
    try:
        payload = decode_token(refresh_token)
    except JWTError:
        raise HTTPException(status_code=401, detail="Invalid or expired refresh token")

    if payload.get("type") != TokenType.REFRESH.value:
        raise HTTPException(status_code=401, detail="Invalid token type")

    result = await db.execute(
        select(User).where(User.id == uuid.UUID(payload["sub"]), User.deleted_at.is_(None))
    )
    user = result.scalar_one_or_none()
    if user is None or not user.is_active:
        raise HTTPException(status_code=401, detail="User no longer valid")

    return issue_token_pair(user)


async def verify_email(db: AsyncSession, token: str) -> User:
    result = await db.execute(
        select(AuthToken).where(
            AuthToken.token == token,
            AuthToken.purpose == AuthTokenPurpose.EMAIL_VERIFICATION.value,
            AuthToken.used.is_(False),
        )
    )
    auth_token = result.scalar_one_or_none()
    if auth_token is None or auth_token.expires_at < datetime.now(timezone.utc):
        raise HTTPException(status_code=400, detail="Invalid or expired verification token")

    user_result = await db.execute(select(User).where(User.id == auth_token.user_id))
    user = user_result.scalar_one_or_none()
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")

    user.is_email_verified = True
    auth_token.used = True
    await db.commit()
    await db.refresh(user)
    return user


async def create_password_reset_token(
    db: AsyncSession, email: str, notification_provider: EmailProvider
) -> AuthToken | None:
    result = await db.execute(select(User).where(User.email == email.lower()))
    user = result.scalar_one_or_none()
    if user is None:
        # Do not reveal whether the email exists — return None and let the
        # router respond with a generic 202 either way.
        return None

    reset_token = AuthToken(
        user_id=user.id,
        token=secrets.token_urlsafe(32),
        purpose=AuthTokenPurpose.PASSWORD_RESET.value,
        expires_at=datetime.now(timezone.utc) + timedelta(hours=RESET_TOKEN_TTL_HOURS),
    )
    db.add(reset_token)
    await db.commit()
    await db.refresh(reset_token)

    reset_url = f"{settings.FRONTEND_BASE_URL}/reset-password?token={reset_token.token}"
    notification_provider.send_email(
        to=user.email,
        subject="Reset your AegisAI password",
        body=f"Reset your password: {reset_url}\n\nThis link expires in {RESET_TOKEN_TTL_HOURS} hour(s). If you didn't request this, ignore this email.",
    )

    return reset_token


async def reset_password(db: AsyncSession, token: str, new_password: str) -> None:
    result = await db.execute(
        select(AuthToken).where(
            AuthToken.token == token,
            AuthToken.purpose == AuthTokenPurpose.PASSWORD_RESET.value,
            AuthToken.used.is_(False),
        )
    )
    auth_token = result.scalar_one_or_none()
    if auth_token is None or auth_token.expires_at < datetime.now(timezone.utc):
        raise HTTPException(status_code=400, detail="Invalid or expired reset token")

    user_result = await db.execute(select(User).where(User.id == auth_token.user_id))
    user = user_result.scalar_one_or_none()
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")

    user.hashed_password = hash_password(new_password)
    auth_token.used = True
    await db.commit()
