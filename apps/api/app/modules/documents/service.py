"""
Business logic for documents: upload, versioning, retrieval, deletion.

Upload flow (both "new document" and "new version" of an existing one):
  1. Validate content type + size.
  2. Compute checksum, build a storage key, upload bytes to the storage
     backend.
  3. Create the DocumentVersion row with status=pending.
  4. Enqueue the Celery processing task (extraction + chunking).

Step 4 is a plain function call to `enqueue_processing`, which callers can
monkeypatch/override in tests to run synchronously instead of hitting a
real Celery broker.
"""
import hashlib
import uuid
from typing import Callable

from fastapi import HTTPException, UploadFile, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.modules.documents.models import Document, DocumentChunk, DocumentStatus, DocumentVersion
from app.modules.documents.storage import StorageBackend

settings = get_settings()

MAX_FILENAME_LENGTH = 500


async def _validate_upload(file: UploadFile, data: bytes) -> None:
    if file.content_type not in settings.ALLOWED_UPLOAD_CONTENT_TYPES:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail=(
                f"Unsupported file type '{file.content_type}'. "
                f"Allowed: PDF, DOCX, Markdown, TXT."
            ),
        )
    if len(data) > settings.MAX_UPLOAD_SIZE_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"File exceeds maximum size of {settings.MAX_UPLOAD_SIZE_BYTES} bytes",
        )
    if not data:
        raise HTTPException(status_code=400, detail="Uploaded file is empty")


def _build_storage_key(org_id: uuid.UUID, document_id: uuid.UUID, version: int, filename: str) -> str:
    return f"orgs/{org_id}/documents/{document_id}/v{version}/{filename}"


async def create_document(
    db: AsyncSession,
    storage: StorageBackend,
    org_id: uuid.UUID,
    uploaded_by_id: uuid.UUID,
    file: UploadFile,
    enqueue_processing: Callable[[uuid.UUID], None],
) -> Document:
    data = await file.read()
    await _validate_upload(file, data)

    document = Document(
        organization_id=org_id,
        uploaded_by_id=uploaded_by_id,
        filename=file.filename[:MAX_FILENAME_LENGTH],
        content_type=file.content_type,
        latest_version_number=1,
    )
    db.add(document)
    await db.flush()  # obtain document.id

    checksum = hashlib.sha256(data).hexdigest()
    storage_key = _build_storage_key(org_id, document.id, 1, document.filename)

    version = DocumentVersion(
        document_id=document.id,
        version_number=1,
        storage_key=storage_key,
        size_bytes=len(data),
        checksum_sha256=checksum,
        status=DocumentStatus.PENDING.value,
    )
    db.add(version)
    await db.flush()

    storage.upload(storage_key, data, file.content_type)

    await db.commit()
    await db.refresh(document)
    await db.refresh(version)

    enqueue_processing(version.id)
    return document


async def create_new_version(
    db: AsyncSession,
    storage: StorageBackend,
    document: Document,
    file: UploadFile,
    enqueue_processing: Callable[[uuid.UUID], None],
) -> DocumentVersion:
    data = await file.read()
    await _validate_upload(file, data)

    next_version_number = document.latest_version_number + 1
    checksum = hashlib.sha256(data).hexdigest()
    storage_key = _build_storage_key(
        document.organization_id, document.id, next_version_number, file.filename
    )

    version = DocumentVersion(
        document_id=document.id,
        version_number=next_version_number,
        storage_key=storage_key,
        size_bytes=len(data),
        checksum_sha256=checksum,
        status=DocumentStatus.PENDING.value,
    )
    db.add(version)

    document.latest_version_number = next_version_number
    document.content_type = file.content_type

    storage.upload(storage_key, data, file.content_type)

    await db.commit()
    await db.refresh(version)

    enqueue_processing(version.id)
    return version


async def get_document(db: AsyncSession, org_id: uuid.UUID, document_id: uuid.UUID) -> Document:
    result = await db.execute(
        select(Document).where(
            Document.id == document_id,
            Document.organization_id == org_id,
            Document.deleted_at.is_(None),
        )
    )
    document = result.scalar_one_or_none()
    if document is None:
        raise HTTPException(status_code=404, detail="Document not found")
    return document


async def list_documents(db: AsyncSession, org_id: uuid.UUID) -> list[Document]:
    result = await db.execute(
        select(Document)
        .where(Document.organization_id == org_id, Document.deleted_at.is_(None))
        .order_by(Document.created_at.desc())
    )
    return list(result.scalars().all())


async def list_versions(db: AsyncSession, document_id: uuid.UUID) -> list[DocumentVersion]:
    result = await db.execute(
        select(DocumentVersion)
        .where(DocumentVersion.document_id == document_id)
        .order_by(DocumentVersion.version_number.desc())
    )
    return list(result.scalars().all())


async def get_latest_version(db: AsyncSession, document_id: uuid.UUID) -> DocumentVersion | None:
    result = await db.execute(
        select(DocumentVersion)
        .where(DocumentVersion.document_id == document_id)
        .order_by(DocumentVersion.version_number.desc())
        .limit(1)
    )
    return result.scalar_one_or_none()


async def list_chunks_for_version(
    db: AsyncSession, version_id: uuid.UUID
) -> list[DocumentChunk]:
    result = await db.execute(
        select(DocumentChunk)
        .where(DocumentChunk.document_version_id == version_id)
        .order_by(DocumentChunk.chunk_index)
    )
    return list(result.scalars().all())


async def soft_delete_document(db: AsyncSession, document: Document) -> None:
    from datetime import datetime, timezone

    document.deleted_at = datetime.now(timezone.utc)
    await db.commit()
