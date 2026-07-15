"""
Request-logging middleware.

Best-effort audit trail for every API request (the middleware itself
never blocks or fails the request — `audit.service.record_event` swallows
its own errors). Skips a small set of noisy/non-informative paths
(health check, docs). User/org identity is extracted best-effort: the
Authorization header is decoded manually here since middleware runs
outside FastAPI's dependency-injection system, and `org_id` is read from
the resolved route's path params (populated by Starlette's routing by the
time `call_next` returns).

The session factory is read from `request.app.state.audit_session_factory`
rather than imported directly — middleware sits outside FastAPI's
`Depends()` system, so `app.dependency_overrides` (which is how every
other module's DB access gets swapped to a test database) has no effect
on a plain module-level import. Storing the factory on `app.state` gives
tests the same swap point without requiring a second DI mechanism.
"""
import time
import uuid

from jose import JWTError
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request

from app.core.security import decode_token

_SKIP_PATHS = {"/health", "/api/docs", "/api/redoc", "/openapi.json"}


class AuditRequestMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        started = time.monotonic()
        response = await call_next(request)

        if request.url.path in _SKIP_PATHS:
            return response

        latency_ms = int((time.monotonic() - started) * 1000)

        user_id = None
        auth_header = request.headers.get("authorization", "")
        if auth_header.lower().startswith("bearer "):
            try:
                payload = decode_token(auth_header[7:])
                if payload.get("type") == "access":
                    user_id = uuid.UUID(payload["sub"])
            except (JWTError, ValueError, KeyError):
                pass

        org_id = None
        raw_org_id = request.path_params.get("org_id")
        if raw_org_id:
            try:
                org_id = raw_org_id if isinstance(raw_org_id, uuid.UUID) else uuid.UUID(str(raw_org_id))
            except (ValueError, TypeError):
                pass

        from app.modules.audit.service import record_event

        session_factory = request.app.state.audit_session_factory
        async with session_factory() as db:
            await record_event(
                db,
                event_type="api_request",
                organization_id=org_id,
                user_id=user_id,
                method=request.method,
                path=request.url.path,
                status_code=response.status_code,
                ip_address=request.client.host if request.client else None,
                latency_ms=latency_ms,
            )

        return response
