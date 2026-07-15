"""
Database engine and session management.

Uses SQLAlchemy 2.0 async engine. A single engine is created per process and
reused; sessions are created per-request via the `get_db` dependency so each
request gets an isolated transaction scope.
"""
from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase

from app.core.config import get_settings

settings = get_settings()

# SQLite (used in the test suite) doesn't support the QueuePool sizing
# arguments that Postgres does — only pass them for real Postgres engines.
_engine_kwargs: dict = {"echo": settings.DEBUG, "pool_pre_ping": True}
if not settings.DATABASE_URL.startswith("sqlite"):
    _engine_kwargs["pool_size"] = 10
    _engine_kwargs["max_overflow"] = 20

engine = create_async_engine(settings.DATABASE_URL, **_engine_kwargs)

AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=False,
)


class Base(DeclarativeBase):
    """Shared declarative base for all ORM models across modules."""
    pass


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """
    FastAPI dependency that yields a request-scoped async DB session and
    guarantees rollback on error / close on completion.
    """
    async with AsyncSessionLocal() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


# --- Sync engine for Celery tasks ---
#
# Celery workers run tasks in plain (non-async) function calls. Rather than
# forcing every task to spin up its own event loop to use the async engine,
# background tasks use a conventional sync SQLAlchemy session instead. Both
# engines point at the same database — this only affects the driver used to
# get there (asyncpg vs psycopg2).
from sqlalchemy import create_engine  # noqa: E402
from sqlalchemy.orm import Session, sessionmaker  # noqa: E402


def _sync_database_url(async_url: str) -> str:
    if async_url.startswith("postgresql+asyncpg://"):
        return async_url.replace("postgresql+asyncpg://", "postgresql+psycopg2://", 1)
    if async_url.startswith("sqlite+aiosqlite://"):
        return async_url.replace("sqlite+aiosqlite://", "sqlite://", 1)
    return async_url


sync_engine = create_engine(_sync_database_url(settings.DATABASE_URL), pool_pre_ping=True)
SyncSessionLocal = sessionmaker(bind=sync_engine, expire_on_commit=False)


def get_sync_db() -> Session:
    """Plain (non-generator) sync session factory for use inside Celery tasks."""
    return SyncSessionLocal()
