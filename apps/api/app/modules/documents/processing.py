"""
Document processing pipeline: extract text from a version's stored file,
chunk it, embed each chunk, persist chunks + upsert into the vector store,
and update the version's status.

`process_document_version_sync` is the actual logic and takes a plain sync
SQLAlchemy `Session` — it has no Celery or FastAPI dependency, so it's
directly unit-testable and directly callable from a Celery task (which
runs sync code) without an event loop.
"""
import logging

from sqlalchemy.orm import Session

from aegis_ai_core.embeddings import EmbeddingProvider
from aegis_ai_core.vector_store import VectorStoreBackend

from app.modules.documents.extraction import chunk_text, extract_text
from app.modules.documents.models import DocumentChunk, DocumentStatus, DocumentVersion
from app.modules.documents.storage import StorageBackend

logger = logging.getLogger(__name__)


def process_document_version_sync(
    db: Session,
    storage: StorageBackend,
    embedding_provider: EmbeddingProvider,
    vector_store: VectorStoreBackend,
    version_id,
) -> DocumentVersion:
    version = db.get(DocumentVersion, version_id)
    if version is None:
        raise ValueError(f"DocumentVersion {version_id} not found")

    version.status = DocumentStatus.PROCESSING.value
    db.commit()

    try:
        data = storage.download(version.storage_key)
        document = version.document
        result = extract_text(document.content_type, data)

        if not result.text.strip():
            version.status = DocumentStatus.NEEDS_OCR.value
            version.page_count = result.page_count
            db.commit()
            return version

        chunk_texts = chunk_text(result.text)
        embeddings = embedding_provider.embed_batch(chunk_texts) if chunk_texts else []

        chunks: list[DocumentChunk] = []
        for index, (chunk_content, vector) in enumerate(zip(chunk_texts, embeddings)):
            chunk = DocumentChunk(
                document_version_id=version.id,
                chunk_index=index,
                content=chunk_content,
                token_count=len(chunk_content.split()),
                embedding=vector,
                chunk_metadata={},
            )
            db.add(chunk)
            chunks.append(chunk)

        db.flush()  # obtain chunk.id for each chunk before upserting to the vector store

        for chunk, vector in zip(chunks, embeddings):
            vector_store.upsert(
                organization_id=str(document.organization_id),
                chunk_id=str(chunk.id),
                vector=vector,
                metadata={
                    "document_id": str(document.id),
                    "document_version_id": str(version.id),
                    "chunk_index": chunk.chunk_index,
                    "content": chunk.content,
                    "filename": document.filename,
                },
            )

        version.page_count = result.page_count
        version.status = DocumentStatus.COMPLETED.value
        db.commit()
        return version

    except Exception as exc:  # noqa: BLE001 — must never let a bad file crash the worker
        logger.exception("Document processing failed for version %s", version_id)
        db.rollback()
        version = db.get(DocumentVersion, version_id)
        version.status = DocumentStatus.FAILED.value
        version.error_message = str(exc)[:2000]
        db.commit()
        return version
