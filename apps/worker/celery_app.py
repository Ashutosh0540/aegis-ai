"""
Worker process entrypoint.

The actual Celery app lives in `app.core.celery_app` so the API process can
import the same instance to enqueue tasks. This module just re-exports it
under the name the `celery` CLI command points at (see Dockerfile CMD).
"""
from app.core.celery_app import celery_app  # noqa: F401
