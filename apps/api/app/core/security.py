"""
Security primitives: password hashing and JWT issuance/verification.

Isolated here so every module (and future modules like documents/chat) uses
one consistent, audited implementation rather than ad-hoc jose/passlib calls
scattered across the codebase.
"""
import uuid
from datetime import datetime, timedelta, timezone
from enum import Enum

from jose import JWTError, jwt
from passlib.context import CryptContext

from app.core.config import get_settings

settings = get_settings()

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


class TokenType(str, Enum):
    ACCESS = "access"
    REFRESH = "refresh"


def hash_password(plain_password: str) -> str:
    return pwd_context.hash(plain_password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    return pwd_context.verify(plain_password, hashed_password)


def create_token(
    subject: uuid.UUID | str,
    token_type: TokenType,
    extra_claims: dict | None = None,
) -> str:
    """
    Create a signed JWT.

    `subject` is the user id. `extra_claims` typically carries org_id / roles
    so downstream modules can authorize without an extra DB round trip.
    """
    now = datetime.now(timezone.utc)
    if token_type == TokenType.ACCESS:
        expire = now + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    else:
        expire = now + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS)

    payload = {
        "sub": str(subject),
        "type": token_type.value,
        "iat": now,
        "exp": expire,
        "jti": str(uuid.uuid4()),
    }
    if extra_claims:
        payload.update(extra_claims)

    return jwt.encode(payload, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM)


def decode_token(token: str) -> dict:
    """
    Decode and validate a JWT. Raises jose.JWTError on any failure
    (expired, bad signature, malformed) — callers translate this into a
    401 at the API boundary.
    """
    try:
        return jwt.decode(token, settings.JWT_SECRET_KEY, algorithms=[settings.JWT_ALGORITHM])
    except JWTError as exc:
        raise exc
