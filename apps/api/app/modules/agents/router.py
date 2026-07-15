"""
HTTP routes for agents.

`GET /api/v1/agents` is deliberately NOT org-scoped — it's a static
capability listing (which agents exist platform-wide), not tenant data.
Everything else (invoke, run history) is scoped under
`/organizations/{org_id}/agents` like every other tenant resource.
"""
import uuid

from aegis_ai_core.embeddings import EmbeddingProvider
from aegis_ai_core.llm import LLMProvider
from aegis_ai_core.vector_store import VectorStoreBackend
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.ai_providers import get_embedding_provider, get_llm_provider, get_vector_store
from app.core.database import get_db
from app.core.deps import RequireOrgRole, get_current_active_user
from app.core.n8n_client import N8nClient, get_n8n_client
from app.core.notifications import EmailProvider, get_notification_provider
from app.modules.agents import service
from app.modules.agents.schemas import AgentInfo, AgentInvokeRequest, AgentRunRead
from app.modules.organizations.models import OrgRole
from app.modules.users.models import User

router = APIRouter(tags=["agents"])

_any_member = RequireOrgRole(OrgRole.OWNER.value, OrgRole.ADMIN.value, OrgRole.MEMBER.value)


@router.get("/agents", response_model=list[AgentInfo])
async def list_agents():
    return service.list_available_agents()


@router.post(
    "/organizations/{org_id}/agents/invoke",
    response_model=AgentRunRead,
    status_code=201,
    dependencies=[Depends(_any_member)],
)
async def invoke_agent(
    org_id: uuid.UUID,
    payload: AgentInvokeRequest,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
    embedding_provider: EmbeddingProvider = Depends(get_embedding_provider),
    vector_store: VectorStoreBackend = Depends(get_vector_store),
    llm_provider: LLMProvider = Depends(get_llm_provider),
    notification_provider: EmailProvider = Depends(get_notification_provider),
    n8n_client: N8nClient = Depends(get_n8n_client),
):
    return await service.invoke_agent(
        db,
        org_id,
        current_user.id,
        payload,
        embedding_provider,
        vector_store,
        llm_provider,
        notification_provider,
        n8n_client,
    )


@router.get(
    "/organizations/{org_id}/agents/runs",
    response_model=list[AgentRunRead],
    dependencies=[Depends(_any_member)],
)
async def list_agent_runs(org_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    return await service.list_agent_runs(db, org_id)
