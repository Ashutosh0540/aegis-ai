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
    curl \
    && rm -rf /var/lib/apt/lists/*

# Shared AI/RAG package (embeddings, vector store, LLM providers) — used by
# both this service and the worker. Installed editable so both consume the
# exact same source without vendoring a copy into each image.
COPY packages/ai /packages/ai
RUN pip install --default-timeout=300 --retries=10 -e /packages/ai

COPY apps/api/requirements.txt .
RUN pip install --default-timeout=300 --retries=10 -r requirements.txt

COPY apps/api/ .

RUN useradd --create-home --shell /bin/bash appuser \
    && chown -R appuser:appuser /app
USER appuser

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
