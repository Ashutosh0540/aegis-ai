"""HTTP routes for /api/v1/organizations/{org_id}/analytics."""
import uuid

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.deps import RequireOrgRole
from app.modules.analytics import service
from app.modules.analytics.schemas import OrganizationOverview
from app.modules.organizations.models import OrgRole

router = APIRouter(prefix="/organizations/{org_id}/analytics", tags=["analytics"])

_any_member = RequireOrgRole(OrgRole.OWNER.value, OrgRole.ADMIN.value, OrgRole.MEMBER.value)


@router.get("/overview", response_model=OrganizationOverview, dependencies=[Depends(_any_member)])
async def get_overview(org_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    return await service.get_organization_overview(db, org_id)
