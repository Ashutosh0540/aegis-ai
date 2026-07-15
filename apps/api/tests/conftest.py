"""
Shared test fixtures.

Tests run against SQLite (via aiosqlite for the async app, and the stdlib
sqlite3 driver for a sync engine) rather than Postgres, for speed and CI
simplicity. A temp *file* (not :memory:) is used per test so the async and
sync engines both see the same data — this matters for the documents
module, where upload happens via the async API but processing runs via a
sync SQLAlchemy session (mirroring how Celery workers operate in
production).
"""
import os
import tempfile
import uuid

os.environ.setdefault("JWT_SECRET_KEY", "test-secret-key-do-not-use-in-production")
os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///:memory:")

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import create_engine
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.orm import sessionmaker

from app.core.database import Base, get_db
from app.core.ai_providers import get_embedding_provider, get_llm_provider, get_vector_store
from app.main import app
from app.modules.auth.router import limiter

# Import models so tables are registered on Base.metadata.
from app.modules.users.models import User  # noqa: F401
from app.modules.organizations.models import (  # noqa: F401
    Organization,
    OrganizationInvite,
    OrganizationMember,
)
from app.modules.auth.models import AuthToken  # noqa: F401
from app.modules.documents.models import Document, DocumentChunk, DocumentVersion  # noqa: F401
from app.modules.chat.models import ChatMessage, Conversation  # noqa: F401
from app.modules.agents.models import AgentRun  # noqa: F401
from app.modules.workflows.models import Ticket  # noqa: F401
from app.modules.audit.models import AuditLog  # noqa: F401
from app.modules.documents.router import get_enqueue_processing
from app.modules.documents.storage import get_storage_backend
from app.core.notifications import get_notification_provider
from app.core.n8n_client import get_n8n_client

from aegis_ai_core.embeddings import FakeEmbeddingProvider
from aegis_ai_core.llm import FakeLLMProvider
from aegis_ai_core.vector_store import FAISSVectorStore
from app.core.notifications import FakeEmailProvider
from app.core.n8n_client import FakeN8nClient


class FakeStorageBackend:
    """In-memory stand-in for S3StorageBackend — no MinIO/S3 required in tests."""

    def __init__(self):
        self._objects: dict[str, bytes] = {}

    def upload(self, key: str, data: bytes, content_type: str) -> None:
        self._objects[key] = data

    def download(self, key: str) -> bytes:
        return self._objects[key]

    def delete(self, key: str) -> None:
        self._objects.pop(key, None)


_engine_db_paths: dict[int, str] = {}


@pytest_asyncio.fixture
async def test_engine():
    db_path = os.path.join(tempfile.mkdtemp(), "test.db")
    db_url = f"sqlite+aiosqlite:///{db_path}"
    engine = create_async_engine(db_url, connect_args={"check_same_thread": False})
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    _engine_db_paths[id(engine)] = db_path
    yield engine
    del _engine_db_paths[id(engine)]
    await engine.dispose()


@pytest_asyncio.fixture
async def db_session(test_engine):
    session_factory = async_sessionmaker(bind=test_engine, expire_on_commit=False)
    async with session_factory() as session:
        yield session


@pytest.fixture
def sync_session_factory(test_engine):
    """Sync sessionmaker pointed at the same SQLite file as the async engine —
    used to run document processing in-process, mirroring the Celery worker."""
    db_path = _engine_db_paths[id(test_engine)]
    sync_engine = create_engine(f"sqlite:///{db_path}")
    return sessionmaker(bind=sync_engine, expire_on_commit=False)


@pytest.fixture
def fake_storage():
    return FakeStorageBackend()


@pytest.fixture
def fake_embedding_provider():
    return FakeEmbeddingProvider(dimension=64)


@pytest.fixture
def fake_llm_provider():
    return FakeLLMProvider()


@pytest.fixture
def test_vector_store():
    """A real FAISSVectorStore, backed by a fresh temp directory per test —
    no test double needed here since FAISS itself has no network dependency."""
    return FAISSVectorStore(tempfile.mkdtemp())


@pytest.fixture
def fake_email_provider():
    return FakeEmailProvider()


@pytest.fixture
def fake_n8n_client():
    return FakeN8nClient()


@pytest_asyncio.fixture
async def client(
    test_engine,
    sync_session_factory,
    fake_storage,
    fake_embedding_provider,
    fake_llm_provider,
    test_vector_store,
    fake_email_provider,
    fake_n8n_client,
):
    session_factory = async_sessionmaker(bind=test_engine, expire_on_commit=False)

    async def override_get_db():
        async with session_factory() as session:
            yield session

    def override_get_storage_backend():
        return fake_storage

    def override_get_embedding_provider():
        return fake_embedding_provider

    def override_get_vector_store():
        return test_vector_store

    def override_get_llm_provider():
        return fake_llm_provider

    def override_get_notification_provider():
        return fake_email_provider

    def override_get_n8n_client():
        return fake_n8n_client

    def override_get_enqueue_processing():
        from app.modules.documents.processing import process_document_version_sync

        def synchronous_enqueue(version_id: uuid.UUID) -> None:
            # Mirrors what the Celery task does, but runs inline so tests
            # don't need a live Redis broker + worker process.
            db = sync_session_factory()
            try:
                process_document_version_sync(
                    db, fake_storage, fake_embedding_provider, test_vector_store, version_id
                )
            finally:
                db.close()

        return synchronous_enqueue

    app.dependency_overrides[get_db] = override_get_db
    app.state.audit_session_factory = session_factory
    app.dependency_overrides[get_storage_backend] = override_get_storage_backend
    app.dependency_overrides[get_embedding_provider] = override_get_embedding_provider
    app.dependency_overrides[get_vector_store] = override_get_vector_store
    app.dependency_overrides[get_llm_provider] = override_get_llm_provider
    app.dependency_overrides[get_notification_provider] = override_get_notification_provider
    app.dependency_overrides[get_n8n_client] = override_get_n8n_client
    app.dependency_overrides[get_enqueue_processing] = override_get_enqueue_processing
    limiter.reset()  # each test gets a fresh rate-limit window
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
    app.dependency_overrides.clear()
