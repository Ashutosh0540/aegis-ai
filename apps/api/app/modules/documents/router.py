"""
HTTP routes for /api/v1/organizations/{org_id}/documents.

All routes are scoped by org_id and require the caller to be a member of
that organization (any role can upload/read; delete requires owner/admin).
"""
import uuid
from concurrent.futures import ThreadPoolExecutor
from functools import partial

from fastapi import APIRouter, Depends, File, UploadFile

from app.core.database import get_db, SyncSessionLocal
from app.core.deps import RequireOrgRole, get_current_active_user
from app.modules.documents import service
from app.modules.documents.schemas import (
    DocumentChunkRead,
    DocumentRead,
    DocumentVersionRead,
    DocumentWithLatestVersion,
)
from app.modules.documents.storage import StorageBackend, get_storage_backend
from app.modules.organizations.models import OrgRole
from app.modules.users.models import User
from sqlalchemy.ext.asyncio import AsyncSession

router = APIRouter(prefix="/organizations/{org_id}/documents", tags=["documents"])

_any_member = RequireOrgRole(OrgRole.OWNER.value, OrgRole.ADMIN.value, OrgRole.MEMBER.value)
_admin_or_owner = RequireOrgRole(OrgRole.OWNER.value, OrgRole.ADMIN.value)

# Thread pool for synchronous document processing
_thread_pool = ThreadPoolExecutor(max_workers=4)


def _process_document_sync(version_id: uuid.UUID) -> None:
    """Process a document synchronously in a background thread."""
    try:
        from app.modules.documents.processing import process_document_version_sync
        from app.core.ai_providers import get_embedding_provider, get_vector_store
        
        # Get a fresh sync session for this thread
        db = SyncSessionLocal()
        try:
            storage = get_storage_backend()
            embedding_provider = get_embedding_provider()
            vector_store = get_vector_store()
            process_document_version_sync(db, storage, embedding_provider, vector_store, version_id)
        finally:
            db.close()
    except Exception as exc:
        import logging
        logger = logging.getLogger(__name__)
        logger.exception(f"Synchronous document processing failed for version {version_id}: {exc}")


def _default_enqueue(version_id: uuid.UUID) -> None:
    """Enqueue the document processing task."""
    try:
        from app.modules.documents.tasks import process_document_version_task
        process_document_version_task.delay(str(version_id))
    except Exception:
        # If Celery/Redis is not available, process synchronously in a thread pool
        _thread_pool.submit(_process_document_sync, version_id)


def get_enqueue_processing():
    """
    FastAPI dependency returning the enqueue callable.

    Overridden in tests (see tests/conftest.py) to process synchronously
    in-process instead of requiring a live Redis broker + worker.
    
    In local development, falls back to thread-based processing if Redis/Celery is unavailable.
    """
    return _default_enqueue


@router.post("", response_model=DocumentRead, status_code=201, dependencies=[Depends(_any_member)])
async def upload_document(
    org_id: uuid.UUID,
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
    storage: StorageBackend = Depends(get_storage_backend),
    enqueue_processing=Depends(get_enqueue_processing),
):
    return await service.create_document(
        db, storage, org_id, current_user.id, file, enqueue_processing=enqueue_processing
    )


@router.get("", response_model=list[DocumentRead], dependencies=[Depends(_any_member)])
async def list_documents(org_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    return await service.list_documents(db, org_id)


@router.get(
    "/{document_id}",
    response_model=DocumentWithLatestVersion,
    dependencies=[Depends(_any_member)],
)
async def get_document(org_id: uuid.UUID, document_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    document = await service.get_document(db, org_id, document_id)
    latest_version = await service.get_latest_version(db, document.id)
    result = DocumentWithLatestVersion.model_validate(document)
    if latest_version is not None:
        result.latest_version = DocumentVersionRead.model_validate(latest_version)
    return result


@router.post(
    "/{document_id}/versions",
    response_model=DocumentVersionRead,
    status_code=201,
    dependencies=[Depends(_any_member)],
)
async def upload_new_version(
    org_id: uuid.UUID,
    document_id: uuid.UUID,
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    storage: StorageBackend = Depends(get_storage_backend),
    enqueue_processing=Depends(get_enqueue_processing),
):
    document = await service.get_document(db, org_id, document_id)
    return await service.create_new_version(db, storage, document, file, enqueue_processing=enqueue_processing)


@router.get(
    "/{document_id}/versions",
    response_model=list[DocumentVersionRead],
    dependencies=[Depends(_any_member)],
)
async def list_versions(
    org_id: uuid.UUID, document_id: uuid.UUID, db: AsyncSession = Depends(get_db)
):
    await service.get_document(db, org_id, document_id)  # 404s if not found/wrong org
    return await service.list_versions(db, document_id)


@router.get(
    "/{document_id}/chunks",
    response_model=list[DocumentChunkRead],
    dependencies=[Depends(_any_member)],
)
async def get_latest_chunks(
    org_id: uuid.UUID, document_id: uuid.UUID, db: AsyncSession = Depends(get_db)
):
    document = await service.get_document(db, org_id, document_id)
    latest_version = await service.get_latest_version(db, document.id)
    if latest_version is None:
        return []
    return await service.list_chunks_for_version(db, latest_version.id)


@router.delete("/{document_id}", status_code=204, dependencies=[Depends(_admin_or_owner)])
async def delete_document(org_id: uuid.UUID, document_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    document = await service.get_document(db, org_id, document_id)
    await service.soft_delete_document(db, document)
