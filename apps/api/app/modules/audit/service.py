"""
Business logic for audit logging.

`record_event` is the single write path — called from the request-logging
middleware (`app.core.audit_middleware`) for every API request, and
explicitly from `auth.service` for security events (login failure,
password reset). It never raises: a failure to write an audit row must
never break the request that triggered it, so errors are swallowed after
a rollback (the alternative — audit logging taking down the API — is
worse than an occasional missed audit row).
"""
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.audit.models import AuditLog


async def record_event(
    db: AsyncSession,
    event_type: str,
    organization_id: uuid.UUID | None = None,
    user_id: uuid.UUID | None = None,
    resource_type: str | None = None,
    resource_id: str | None = None,
    method: str | None = None,
    path: str | None = None,
    status_code: int | None = None,
    ip_address: str | None = None,
    latency_ms: int | None = None,
    event_metadata: dict | None = None,
) -> None:
    try:
        db.add(
            AuditLog(
                organization_id=organization_id,
                user_id=user_id,
                event_type=event_type,
                resource_type=resource_type,
                resource_id=resource_id,
                method=method,
                path=path,
                status_code=status_code,
                ip_address=ip_address,
                latency_ms=latency_ms,
                event_metadata=event_metadata or {},
            )
        )
        await db.commit()
    except Exception:  # noqa: BLE001 — audit logging must never break the request
        await db.rollback()


async def list_audit_logs(
    db: AsyncSession, org_id: uuid.UUID, event_type: str | None = None, limit: int = 200
) -> list[AuditLog]:
    query = select(AuditLog).where(AuditLog.organization_id == org_id)
    if event_type:
        query = query.where(AuditLog.event_type == event_type)
    query = query.order_by(AuditLog.created_at.desc()).limit(limit)
    result = await db.execute(query)
    return list(result.scalars().all())
