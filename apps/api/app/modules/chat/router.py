"""HTTP routes for /api/v1/organizations/{org_id}/chat."""
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
from app.modules.chat import service
from app.modules.chat.schemas import (
    ChatMessageCreate,
    ChatMessageRead,
    ConversationCreate,
    ConversationRead,
)
from app.modules.organizations.models import OrgRole
from app.modules.users.models import User

router = APIRouter(prefix="/organizations/{org_id}/chat", tags=["chat"])

_any_member = RequireOrgRole(OrgRole.OWNER.value, OrgRole.ADMIN.value, OrgRole.MEMBER.value)


@router.post(
    "/conversations",
    response_model=ConversationRead,
    status_code=201,
    dependencies=[Depends(_any_member)],
)
async def create_conversation(
    org_id: uuid.UUID,
    payload: ConversationCreate,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    return await service.create_conversation(db, org_id, current_user.id, payload)


@router.get(
    "/conversations", response_model=list[ConversationRead], dependencies=[Depends(_any_member)]
)
async def list_conversations(org_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    return await service.list_conversations(db, org_id)


@router.get(
    "/conversations/{conversation_id}/messages",
    response_model=list[ChatMessageRead],
    dependencies=[Depends(_any_member)],
)
async def list_messages(
    org_id: uuid.UUID, conversation_id: uuid.UUID, db: AsyncSession = Depends(get_db)
):
    await service.get_conversation(db, org_id, conversation_id)  # 404s if not found/wrong org
    return await service.list_messages(db, conversation_id)


@router.post(
    "/conversations/{conversation_id}/messages",
    response_model=ChatMessageRead,
    status_code=201,
    dependencies=[Depends(_any_member)],
)
async def post_message(
    org_id: uuid.UUID,
    conversation_id: uuid.UUID,
    payload: ChatMessageCreate,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
    embedding_provider: EmbeddingProvider = Depends(get_embedding_provider),
    vector_store: VectorStoreBackend = Depends(get_vector_store),
    llm_provider: LLMProvider = Depends(get_llm_provider),
    notification_provider: EmailProvider = Depends(get_notification_provider),
    n8n_client: N8nClient = Depends(get_n8n_client),
):
    conversation = await service.get_conversation(db, org_id, conversation_id)
    return await service.post_message(
        db,
        conversation,
        payload,
        current_user.id,
        embedding_provider,
        vector_store,
        llm_provider,
        notification_provider,
        n8n_client,
    )
