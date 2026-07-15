# CLAUDE_INSTRUCTIONS.md

This is the frozen master specification for AegisAI. Full original spec was
provided as the project's system prompt; this file condenses the rules that
must never be violated.

## Non-negotiable rules
- Modular monolith. NOT microservices. Modules under `apps/api/app/modules/`
  communicate only through service-layer interfaces.
- Each module follows: `models.py` (SQLAlchemy) → `schemas.py` (Pydantic v2)
  → `service.py` (business logic, framework-agnostic) → `router.py` (thin,
  FastAPI, delegates to service via DI).
- UUID PKs, `created_at`/`updated_at`, soft delete (`deleted_at`) on every
  table via the shared mixins in `app/core/models_mixins.py`.
- Every protocol with a real network/IO dependency gets a production
  implementation AND a fake/test implementation (see `StorageBackend`,
  `EmbeddingProvider`, `VectorStoreBackend`, `LLMProvider`, `EmailProvider`,
  `N8nClient`). FAISS is real in tests too (no network needed); HuggingFace
  downloads, Ollama, Pinecone, SMTP, and n8n are faked in tests — this
  sandbox has no network access to those services.
- Shared AI/RAG code (embeddings, vector store, LLM, LangGraph agents) lives
  in `packages/ai/aegis_ai_core`, installed editable into both `apps/api`
  and `apps/worker` images — never duplicated between them.
- Never redesign a module's public contract (schemas, endpoints) to swap
  its internals — see how `chat.service.post_message`'s signature grew
  additively across Milestones 3–5 without breaking existing tests.
- Never skip: architecture explanation → folder structure → code → tests
  → Docker updates → docs → README → run instructions, for each milestone.
- Full tech stack, milestone list, and feature list: see `README.md`.

## Milestones (see README.md status table for current progress)
1. Project setup, Docker, FastAPI, Next.js, Auth, Database, Organizations
2. Documents: upload, storage, processing, metadata
3. RAG: embeddings, FAISS/Pinecone, LangChain
4. LangGraph agents: Supervisor, Knowledge
5. Workflow automation: n8n, email, ticketing
6. Analytics, audit, monitoring, production readiness
