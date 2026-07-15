"""
Object storage abstraction for document files.

Routes and services depend on `StorageBackend`, never on boto3 directly, so
the concrete backend (MinIO locally, AWS S3 in production — they speak the
same API) can be swapped without touching business logic. A fake in-memory
backend is used in tests (see tests/conftest.py) so the suite never needs a
real MinIO/S3 endpoint.
"""
from pathlib import Path
from typing import Protocol

import boto3
from botocore.client import Config as BotoConfig
from botocore.exceptions import ClientError

from app.core.config import get_settings

settings = get_settings()


class StorageBackend(Protocol):
    def upload(self, key: str, data: bytes, content_type: str) -> None: ...
    def download(self, key: str) -> bytes: ...
    def delete(self, key: str) -> None: ...


class S3StorageBackend:
    """S3-compatible backend. Works against MinIO (dev) or AWS S3 (prod)."""

    def __init__(self) -> None:
        self._client = boto3.client(
            "s3",
            endpoint_url=settings.STORAGE_ENDPOINT_URL,
            aws_access_key_id=settings.STORAGE_ACCESS_KEY,
            aws_secret_access_key=settings.STORAGE_SECRET_KEY,
            region_name=settings.STORAGE_REGION,
            use_ssl=settings.STORAGE_USE_SSL,
            config=BotoConfig(signature_version="s3v4"),
        )
        self._bucket = settings.STORAGE_BUCKET
        self._ensure_bucket()

    def _ensure_bucket(self) -> None:
        try:
            self._client.head_bucket(Bucket=self._bucket)
        except ClientError:
            self._client.create_bucket(Bucket=self._bucket)

    def upload(self, key: str, data: bytes, content_type: str) -> None:
        self._client.put_object(
            Bucket=self._bucket, Key=key, Body=data, ContentType=content_type
        )

    def download(self, key: str) -> bytes:
        response = self._client.get_object(Bucket=self._bucket, Key=key)
        return response["Body"].read()

    def delete(self, key: str) -> None:
        self._client.delete_object(Bucket=self._bucket, Key=key)


class LocalFileStorageBackend:
    """Local file-based storage backend for development without MinIO."""

    def __init__(self, storage_dir: str = "./local_storage") -> None:
        self._dir = Path(storage_dir)
        self._dir.mkdir(exist_ok=True, parents=True)

    def upload(self, key: str, data: bytes, content_type: str) -> None:
        file_path = self._dir / key
        file_path.parent.mkdir(exist_ok=True, parents=True)
        file_path.write_bytes(data)

    def download(self, key: str) -> bytes:
        file_path = self._dir / key
        return file_path.read_bytes()

    def delete(self, key: str) -> None:
        file_path = self._dir / key
        if file_path.exists():
            file_path.unlink()


_singleton: StorageBackend | None = None


def get_storage_backend() -> StorageBackend:
    """
    FastAPI dependency / plain accessor for the configured storage backend.
    Lazily constructed and cached so we don't open a new boto3 client per
    request. Overridden in tests via `app.dependency_overrides`.
    
    In development, tries to use S3/MinIO. If that fails, falls back to
    local file storage.
    """
    global _singleton
    if _singleton is None:
        try:
            _singleton = S3StorageBackend()
        except Exception:
            # Fall back to local file storage if MinIO is not available
            _singleton = LocalFileStorageBackend()
    return _singleton
