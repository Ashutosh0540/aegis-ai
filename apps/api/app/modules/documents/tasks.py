"""
Celery tasks for the documents module.

The task itself is a thin wrapper: it opens a sync DB session and the
configured storage/embedding/vector-store backends, then delegates to
`process_document_version_sync`, which holds the actual logic and is
unit-tested directly without going through Celery at all.
"""
import uuid

from app.core.ai_providers import get_embedding_provider, get_vector_store
from app.core.celery_app import celery_app
from app.core.database import SyncSessionLocal
from app.modules.documents.processing import process_document_version_sync
from app.modules.documents.storage import get_storage_backend


@celery_app.task(name="documents.process_version", bind=True, max_retries=2)
def process_document_version_task(self, version_id: str) -> str:
    db = SyncSessionLocal()
    try:
        storage = get_storage_backend()
        embedding_provider = get_embedding_provider()
        vector_store = get_vector_store()
        version = process_document_version_sync(
            db, storage, embedding_provider, vector_store, uuid.UUID(version_id)
        )
        return version.status
    finally:
        db.close()
