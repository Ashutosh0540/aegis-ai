"""HTTP routes for /api/v1/organizations/{org_id}/audit-logs.

Restricted to owner/admin — audit logs can contain sensitive detail
(IPs, request paths, security events) that regular members shouldn't see.
"""
import uuid

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.deps import RequireOrgRole
from app.modules.audit import service
from app.modules.audit.schemas import AuditLogRead
from app.modules.organizations.models import OrgRole

router = APIRouter(prefix="/organizations/{org_id}/audit-logs", tags=["audit"])

_admin_or_owner = RequireOrgRole(OrgRole.OWNER.value, OrgRole.ADMIN.value)


@router.get("", response_model=list[AuditLogRead], dependencies=[Depends(_admin_or_owner)])
async def list_audit_logs(
    org_id: uuid.UUID,
    event_type: str | None = Query(default=None),
    db: AsyncSession = Depends(get_db),
):
    return await service.list_audit_logs(db, org_id, event_type=event_type)
