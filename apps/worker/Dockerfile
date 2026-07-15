# Build context is the repo root (see docker-compose.yml), so this Dockerfile
# can reuse apps/api/app without duplicating module code across images.
FROM python:3.12-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DEFAULT_TIMEOUT=300 \
    PIP_RETRIES=10

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Shared AI/RAG package — same install as apps/api/Dockerfile, see there
# for why this is editable-installed rather than vendored.
COPY packages/ai /packages/ai
RUN pip install --default-timeout=300 --retries=10 -e /packages/ai

COPY apps/worker/requirements.txt .
RUN pip install --default-timeout=300 --retries=10 -r requirements.txt

COPY apps/api/app ./app
COPY apps/worker/celery_app.py .

RUN useradd --create-home --shell /bin/bash appuser \
    && chown -R appuser:appuser /app
USER appuser

CMD ["celery", "-A", "celery_app.celery_app", "worker", "--loglevel=info"]
