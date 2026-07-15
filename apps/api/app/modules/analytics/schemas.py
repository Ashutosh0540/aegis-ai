from pydantic import BaseModel


class OrganizationOverview(BaseModel):
    total_documents: int
    total_document_chunks: int
    total_conversations: int
    total_chat_messages: int
    total_tickets: int
    tickets_by_status: dict[str, int]
    total_agent_runs: int
    agent_runs_by_route: dict[str, int]
    avg_agent_latency_ms: float | None
    estimated_ai_cost_usd: float
