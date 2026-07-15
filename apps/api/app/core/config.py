"""
Centralized application configuration.

All configuration is sourced from environment variables (via .env in local
development, or injected directly in production/container environments).
Never hardcode secrets here — this module only defines shape and defaults
for *non-secret* values.
"""
from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # --- App ---
    APP_NAME: str = "AegisAI"
    ENVIRONMENT: str = "development"  # development | staging | production
    API_V1_PREFIX: str = "/api/v1"
    DEBUG: bool = False

    # --- Security / Auth ---
    JWT_SECRET_KEY: str  # REQUIRED — must be set via environment, no default
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7

    # --- OAuth2 (Google as example provider) ---
    OAUTH_GOOGLE_CLIENT_ID: str | None = None
    OAUTH_GOOGLE_CLIENT_SECRET: str | None = None

    # --- Database ---
    DATABASE_URL: str = (
        "postgresql+asyncpg://aegis:aegis@postgres:5432/aegis_ai"
    )

    # --- Redis / Celery ---
    REDIS_URL: str = "redis://redis:6379/0"
    CELERY_BROKER_URL: str = "redis://redis:6379/1"
    CELERY_RESULT_BACKEND: str = "redis://redis:6379/2"

    # --- CORS ---
    CORS_ORIGINS: list[str] = ["http://localhost:3000"]

    # --- Rate limiting ---
    RATE_LIMIT_PER_MINUTE: int = 100

    # --- Object storage (MinIO in dev, S3-compatible in production) ---
    STORAGE_ENDPOINT_URL: str = "http://minio:9000"
    STORAGE_ACCESS_KEY: str = "aegis_minio"
    STORAGE_SECRET_KEY: str = "aegis_minio_secret"
    STORAGE_BUCKET: str = "aegis-documents"
    STORAGE_REGION: str = "us-east-1"
    STORAGE_USE_SSL: bool = False

    # --- Document processing ---
    MAX_UPLOAD_SIZE_BYTES: int = 25 * 1024 * 1024  # 25 MB
    ALLOWED_UPLOAD_CONTENT_TYPES: list[str] = [
        "application/pdf",
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "text/markdown",
        "text/plain",
    ]
    CHUNK_SIZE_CHARS: int = 1200
    CHUNK_OVERLAP_CHARS: int = 200

    # --- Embeddings (HuggingFace, local — dev and production both) ---
    EMBEDDING_MODEL_NAME: str = "sentence-transformers/all-MiniLM-L6-v2"

    # --- Vector store: FAISS in development, Pinecone in production ---
    FAISS_INDEX_DIR: str = "/app/data/faiss_indices"
    PINECONE_API_KEY: str | None = None
    PINECONE_INDEX_NAME: str = "aegis-ai-documents"

    # --- LLM (Ollama, local — Llama 3 per the tech stack) ---
    OLLAMA_BASE_URL: str = "http://ollama:11434"
    OLLAMA_MODEL: str = "llama3"

    # --- RAG retrieval ---
    RAG_TOP_K: int = 5
    RAG_HISTORY_MESSAGE_LIMIT: int = 10

    # --- Email notifications ---
    # If SMTP_HOST is unset, the app falls back to ConsoleEmailProvider
    # (logs instead of sending) — a safe default for local development
    # rather than a failure.
    SMTP_HOST: str | None = None
    SMTP_PORT: int = 587
    SMTP_USERNAME: str | None = None
    SMTP_PASSWORD: str | None = None
    SMTP_FROM_EMAIL: str = "no-reply@aegis-ai.local"
    SMTP_USE_TLS: bool = True
    FRONTEND_BASE_URL: str = "http://localhost:3000"

    # --- n8n workflow automation ---
    N8N_BASE_URL: str = "http://n8n:5678"
    N8N_WEBHOOK_TIMEOUT_SECONDS: float = 10.0

    # --- LangSmith tracing (off by default; no network call unless enabled) ---
    LANGCHAIN_TRACING_V2: bool = False
    LANGCHAIN_API_KEY: str | None = None
    LANGCHAIN_PROJECT: str = "aegis-ai"
    LANGCHAIN_ENDPOINT: str = "https://api.smith.langchain.com"

    # --- Analytics ---
    # Placeholder flat-rate cost estimate per agent run, since real token-
    # level usage metering isn't implemented yet (Ollama's API doesn't
    # return token counts the way hosted-model APIs do). Replace with
    # real per-token costing once usage metering is built.
    AI_COST_PER_AGENT_RUN_USD: float = 0.01


@lru_cache
def get_settings() -> Settings:
    """Return a cached Settings instance (singleton per process)."""
    return Settings()
