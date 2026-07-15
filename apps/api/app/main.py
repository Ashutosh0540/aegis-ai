"""
AegisAI API — application entrypoint.

Wires together module routers under /api/v1, CORS, rate limiting, and
global exception handling. Business logic never lives here — this file is
purely composition.
"""
from fastapi import FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, Response
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded

from app.core.config import get_settings
from app.core.audit_middleware import AuditRequestMiddleware
from app.core.database import AsyncSessionLocal
from app.core.metrics import METRICS_CONTENT_TYPE, PrometheusMiddleware, render_metrics
from app.core.tracing import configure_langsmith
from app.modules.agents.router import router as agents_router
from app.modules.analytics.router import router as analytics_router
from app.modules.audit.router import router as audit_router
from app.modules.auth.router import limiter, router as auth_router
from app.modules.chat.router import router as chat_router
from app.modules.documents.router import router as documents_router
from app.modules.organizations.router import router as organizations_router
from app.modules.users.router import router as users_router
from app.modules.workflows.router import router as workflows_router

settings = get_settings()
configure_langsmith()

app = FastAPI(
    title=settings.APP_NAME,
    description="Secure AI-powered enterprise workflow automation platform.",
    version="0.1.0",
    docs_url="/api/docs" if settings.ENVIRONMENT != "production" else None,
    redoc_url="/api/redoc" if settings.ENVIRONMENT != "production" else None,
)

app.state.limiter = limiter
app.state.audit_session_factory = AsyncSessionLocal
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

app.add_middleware(AuditRequestMiddleware)
app.add_middleware(PrometheusMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    """
    Catch-all so unexpected errors never leak stack traces to clients.
    Structured logging (with request id, module, and stack) is added in the
    monitoring milestone; for now this guarantees a consistent JSON shape.
    """
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={"detail": "An unexpected error occurred."},
    )


@app.get("/health", tags=["system"])
async def health_check():
    return {"status": "ok", "app": settings.APP_NAME, "environment": settings.ENVIRONMENT}


@app.get("/metrics", tags=["system"])
async def metrics():
    """Prometheus scrape endpoint. Unauthenticated by convention (Prometheus
    exporters are typically firewalled at the network layer, not via app
    auth); see docs/ARCHITECTURE.md Milestone 6 section for the tradeoff."""
    return Response(content=render_metrics(), media_type=METRICS_CONTENT_TYPE)


app.include_router(auth_router, prefix=settings.API_V1_PREFIX)
app.include_router(users_router, prefix=settings.API_V1_PREFIX)
app.include_router(organizations_router, prefix=settings.API_V1_PREFIX)
app.include_router(documents_router, prefix=settings.API_V1_PREFIX)
app.include_router(chat_router, prefix=settings.API_V1_PREFIX)
app.include_router(agents_router, prefix=settings.API_V1_PREFIX)
app.include_router(workflows_router, prefix=settings.API_V1_PREFIX)
app.include_router(audit_router, prefix=settings.API_V1_PREFIX)
app.include_router(analytics_router, prefix=settings.API_V1_PREFIX)
