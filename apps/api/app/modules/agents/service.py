"""
Business logic for the agents module: listing available agents and
running the Supervisor graph ad hoc (outside of a chat conversation),
recording each invocation as an `AgentRun`. Same side-effect handling as
the chat module (`app.core.agent_side_effects`) so a workflow_agent/
email_agent route behaves identically whether triggered via chat or here.
"""
import time
import uuid

from aegis_ai_core.agents import AVAILABLE_AGENTS, run_supervisor_graph
from aegis_ai_core.embeddings import EmbeddingProvider
from aegis_ai_core.llm import LLMProvider
from aegis_ai_core.vector_store import VectorStoreBackend
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.agent_side_effects import apply_agent_side_effects
from app.core.config import get_settings
from app.core.n8n_client import N8nClient
from app.core.notifications import EmailProvider
from app.modules.agents.models import AgentRun, AgentRunStatus
from app.modules.agents.schemas import AgentInfo, AgentInvokeRequest

settings = get_settings()


def list_available_agents() -> list[AgentInfo]:
    return [AgentInfo(**agent) for agent in AVAILABLE_AGENTS]


async def invoke_agent(
    db: AsyncSession,
    org_id: uuid.UUID,
    requested_by_id: uuid.UUID,
    payload: AgentInvokeRequest,
    embedding_provider: EmbeddingProvider,
    vector_store: VectorStoreBackend,
    llm_provider: LLMProvider,
    notification_provider: EmailProvider,
    n8n_client: N8nClient,
) -> AgentRun:
    started = time.monotonic()

    try:
        result = run_supervisor_graph(
            question=payload.input,
            organization_id=str(org_id),
            embedding_provider=embedding_provider,
            vector_store=vector_store,
            llm_provider=llm_provider,
            document_id=str(payload.document_id) if payload.document_id else None,
            top_k=settings.RAG_TOP_K,
        )

        answer = await apply_agent_side_effects(
            db, result, org_id, requested_by_id, notification_provider, n8n_client
        )
        latency_ms = int((time.monotonic() - started) * 1000)

        from app.modules.audit.service import record_event

        await record_event(
            db,
            "agent.invoked",
            organization_id=org_id,
            user_id=requested_by_id,
            event_metadata={"route": result.get("route", "unknown"), "latency_ms": latency_ms},
        )

        run = AgentRun(
            organization_id=org_id,
            requested_by_id=requested_by_id,
            agent_name="supervisor",
            route_taken=result.get("route", "unknown"),
            input_text=payload.input,
            output_text=answer,
            citations=result.get("citations", []),
            status=AgentRunStatus.SUCCESS.value,
            latency_ms=latency_ms,
        )

    except Exception as exc:  # noqa: BLE001 — always record the run, even on failure
        latency_ms = int((time.monotonic() - started) * 1000)
        run = AgentRun(
            organization_id=org_id,
            requested_by_id=requested_by_id,
            agent_name="supervisor",
            route_taken="unknown",
            input_text=payload.input,
            output_text=None,
            citations=[],
            status=AgentRunStatus.ERROR.value,
            error_message=str(exc)[:2000],
            latency_ms=latency_ms,
        )
        db.add(run)
        await db.commit()
        await db.refresh(run)
        return run

    db.add(run)
    await db.commit()
    await db.refresh(run)
    return run


async def list_agent_runs(db: AsyncSession, org_id: uuid.UUID) -> list[AgentRun]:
    result = await db.execute(
        select(AgentRun)
        .where(AgentRun.organization_id == org_id)
        .order_by(AgentRun.created_at.desc())
        .limit(100)
    )
    return list(result.scalars().all())
