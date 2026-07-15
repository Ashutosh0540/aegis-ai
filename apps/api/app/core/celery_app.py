"""
Shared Celery application instance.

Lives under `app.core` (not in apps/worker) so both the API process
(which enqueues tasks via `.delay()`) and the worker process (which
executes them) import the exact same Celery app and task registry,
without a circular dependency between the two deployables.
"""
from celery import Celery

from app.core.config import get_settings
from app.core.tracing import configure_langsmith

settings = get_settings()
configure_langsmith()

celery_app = Celery(
    "aegis_worker",
    broker=settings.CELERY_BROKER_URL,
    backend=settings.CELERY_RESULT_BACKEND,
    include=["app.modules.documents.tasks"],
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    task_track_started=True,
)


@celery_app.task(name="worker.health_check")
def health_check() -> str:
    return "ok"
