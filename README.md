# AegisAI

**Enterprise AI Operations & Knowledge Intelligence Platform**

> Secure AI-powered enterprise workflow automation.

This is a monorepo. See [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) for
the full architecture writeup.

## Status: Milestone 6 of 6 (complete)

| Milestone | Scope | Status |
|---|---|---|
| 1 | Project setup, Docker, FastAPI, Next.js, Auth, Database, Organizations | ✅ Done |
| 2 | Documents: upload, storage, processing, metadata | ✅ Done |
| 3 | RAG: embeddings, FAISS/Pinecone, LangChain | ✅ Done |
| 4 | LangGraph agents: Supervisor, Knowledge | ✅ Done |
| 5 | Workflow automation: n8n, email, ticketing | ✅ Done |
| 6 | Analytics, audit, monitoring, production readiness | ✅ Done |

**Milestone 6 detail:** fully verified. Backend tests pass end-to-end
(`95 passed`) and frontend verification passes (`npm run build` and
`npm run lint`). During final verification, `greenlet==3.1.1` was added
to both `apps/api/requirements.txt` and `apps/worker/requirements.txt`
to satisfy SQLAlchemy async runtime requirements on Python 3.12.

## Repository structure

```
aegis-ai/
├── apps/
│   ├── web/        # Next.js frontend (TypeScript, Tailwind, shadcn/ui)
│   ├── api/         # FastAPI backend (Python 3.12, SQLAlchemy 2, Alembic)
│   └── worker/      # Celery background worker
├── packages/
│   ├── ai/          # Shared: embeddings, vector store (FAISS/Pinecone), LLM providers
│   ├── database/     # (future) shared DB utilities if extracted from api
│   └── shared/       # (future) shared types/utilities
├── workflows/
│   └── n8n/          # (Milestone 5) n8n workflow definitions
├── docs/              # Architecture and design docs
├── docker/            # docker-compose.yml and related config
├── .github/workflows/ # CI
└── tests/             # (module-local tests live inside apps/api/tests for now)
```

## What's implemented in Milestone 1

**Backend (`apps/api`)**
- Auth: register, login, JWT access/refresh tokens, email verification
  tokens, forgot/reset password
- Organizations: create, list, invite members, accept invite, RBAC
  (`owner` / `admin` / `member`)
- Users: read/update own profile
- PostgreSQL via SQLAlchemy 2 (async) + Alembic migration (`0001_initial_schema`)
- Rate limiting on login and forgot-password
- Global exception handling, CORS, health check endpoint
- 15 passing tests (`apps/api/tests/`)

**Frontend (`apps/web`)**
- Landing page, register page, login page, dashboard (protected)
- Organizations: create + list, right from the dashboard
- Documents: upload (PDF/DOCX/Markdown/TXT), list with live status
  polling, delete (`apps/web/app/dashboard/documents`)
- Typed API client (`lib/api-client.ts`)
- Dark-mode-first Tailwind styling
- Verified: `npm run build` and `npm run lint` both pass clean

**Infra**
- Dockerfiles for api, worker, web
- `docker/docker-compose.yml` — Postgres, Redis, MinIO, api, worker, web
- GitHub Actions CI: backend tests + frontend build/lint

## Milestone 2 additions

- **Documents module** (`apps/api/app/modules/documents`): upload, list,
  get, per-document versions, per-version chunks, soft delete — all scoped
  by organization and RBAC-gated (delete requires owner/admin).
- **Storage**: `StorageBackend` protocol + S3-compatible implementation
  (MinIO locally, swappable to real AWS S3 in production).
- **Processing pipeline**: Celery task extracts text (PDF via pypdf, DOCX
  via python-docx, Markdown/TXT as plain text), chunks it (sliding window
  with overlap, paragraph/sentence-boundary aware), and persists
  `DocumentChunk` rows. Status flow: `pending` → `processing` →
  `completed` / `failed` / `needs_ocr`.
- **Versioning**: re-uploading a document creates a new immutable version
  (own storage key, checksum, chunks) without touching prior versions.
- New Alembic migration: `0002_documents` (documents, document_versions,
  document_chunks).
- 14 new tests (extraction/chunking unit tests + full upload→process→chunk
  integration tests) — **29 tests passing** total.

## Milestone 3 additions

- **Shared `packages/ai` package** (`aegis_ai_core`): `EmbeddingProvider`,
  `VectorStoreBackend`, `LLMProvider` protocols, each with a production
  implementation (HuggingFace sentence-transformers / Pinecone / Ollama)
  and — where the real thing needs network access this environment
  doesn't have — a test double. FAISS itself is real in both dev and
  tests, since it needs no network at all.
- **Embedding generation wired into document processing**: every chunk
  produced during Milestone 2's extraction step is now embedded and
  upserted into the vector store (FAISS locally, Pinecone in production),
  scoped by organization.
- **New `chat` module**: conversations + messages, RAG-backed. Posting a
  message embeds the question, retrieves the top-k most relevant chunks
  (optionally scoped to one document), assembles a prompt via a LangChain
  `PromptTemplate` with recent history as memory, generates an answer,
  and stores structured citations (`document_id`, `version_id`,
  `chunk_index`) — not just prose mentioning a filename.
- **Frontend**: `/dashboard/chat` — conversation list, message thread,
  citation chips under each answer.
- New Alembic migration: `0003_chat` (conversations, chat_messages).
- 20 new tests (FAISS retrieval ranking/filtering/persistence, prompt
  assembly, full upload→embed→chat→cite integration flows) — **49 tests
  passing** total.

## Milestone 4 additions

- **`aegis_ai_core.agents`**: a LangGraph graph (`Supervisor →
  KnowledgeAgent → END`). The supervisor node is a real routing decision
  point recorded in graph state, even though only one destination exists
  today — Milestone 5's Email/Meeting/Workflow agents register as new
  routes here without restructuring the graph.
- **`chat.service.post_message` rewired** to call the graph instead of
  the Milestone 3 inline chain — same function signature, same
  `ChatMessage` output shape, every existing chat test passes unchanged.
- **New `agents` module**: `GET /agents` (static capability registry),
  `POST /organizations/{org_id}/agents/invoke` (ad-hoc, non-chat agent
  invocation), `GET /organizations/{org_id}/agents/runs` (audit trail —
  agent, route, latency, status, error on failure).
- New Alembic migration: `0004_agents` (agent_runs).
- 12 new tests (graph routing/retrieval/scoping at the `aegis_ai_core`
  level, plus full API-level invoke/run-history/RBAC tests) — **61 tests
  passing** total.

## Milestone 5 additions

- **Email delivery, finally wired up**: `EmailProvider` protocol
  (`SMTPEmailProvider` production / `ConsoleEmailProvider` dev default /
  `FakeEmailProvider` test). Registration and forgot-password now
  actually send verification/reset emails — closing the TODOs left in
  Milestone 1.
- **n8n integration**: `N8nClient` protocol (`HttpN8nClient` /
  `FakeN8nClient`) triggers webhooks for external workflow automation.
  Ships with an example workflow at `workflows/n8n/ticket-created-
  notification.json`.
- **New `workflows` module**: `Ticket` CRUD
  (`/organizations/{org_id}/tickets`), the concrete "ticket creation"
  feature. Every ticket creation fires an n8n `ticket.created` webhook.
- **Supervisor graph gets real branches**: keyword-based routing across
  `knowledge_agent` (existing), `workflow_agent` (drafts a ticket),
  `email_agent` (drafts, and sends if a recipient is parseable). A chat
  message like *"there's a bug in checkout"* now creates a real `Ticket`
  row; *"send an email to bob@company.com about..."* actually sends via
  the injected `EmailProvider`.
- **Frontend**: `/dashboard/tickets` — create, list, inline status
  updates, with a visible marker for agent-created vs manually-filed
  tickets.
- New Alembic migration: `0005_workflows` (tickets).
- 17 new tests (notification/n8n providers including a real
  unreachable-host error-handling test, ticket CRUD/RBAC, and full
  chat→ticket / chat→email / agent-invoke→ticket end-to-end flows) —
  **78 tests passing** total.

## Milestone 6 additions

- **New `audit` module**: `AuditLog` table + org-scoped
  `GET /organizations/{org_id}/audit-logs` (owner/admin only).
  `AuditRequestMiddleware` logs every API request (method/path/status/
  latency/user/org/IP); login success/failure and AI actions (chat
  messages, agent invocations) are logged explicitly at the point they
  happen.
- **New `analytics` module**: `GET /organizations/{org_id}/analytics/
  overview` — document/chat/ticket/agent-run counts plus an
  explicitly-labeled placeholder AI cost estimate.
- **LangSmith tracing**: `app/core/tracing.py::configure_langsmith()`,
  off by default, zero network calls unless `LANGCHAIN_TRACING_V2=true`.
- **Prometheus metrics**: `GET /metrics` (`http_requests_total`,
  `http_request_duration_seconds`, both labeled by method/route-template/
  status) via a `PrometheusMiddleware` sibling to the audit middleware.
- **Grafana + Prometheus** added to `docker-compose.yml`
  (`prometheus:9090`, `grafana:3001`), with a starter dashboard at
  `workflows/grafana/aegis-ai-overview-dashboard.json` (import manually
  via Grafana's UI, same pattern as the n8n workflow JSON).
- 4 new backend tests (`test_metrics.py`) covering the `/metrics` format,
  counter increments, route-template cardinality control, and the
  scrape-endpoint's own exclusion from its counters — verified as part of
  the full backend suite.



### Option A — Docker Compose (recommended)

```bash
cp apps/api/.env.example apps/api/.env
# edit apps/api/.env and set a real JWT_SECRET_KEY

cd docker
docker compose up --build
```

- API: http://localhost:8000 (docs at `/api/docs`)
- Web: http://localhost:3000
- Postgres: localhost:5432 (`aegis` / `aegis`)
- MinIO console: http://localhost:9001 (`aegis_minio` / `aegis_minio_secret`)
- Ollama: http://localhost:11434 — pull a model once the container is up:
  `docker exec -it $(docker compose -f docker/docker-compose.yml ps -q ollama) ollama pull llama3`
- n8n: http://localhost:5678 — import
  `workflows/n8n/ticket-created-notification.json` to see the example
  ticket-creation automation.
- Prometheus: http://localhost:9090 (scrapes `api:8000/metrics` every 15s)
- Grafana: http://localhost:3001 (`admin` / `admin`) — import
  `workflows/grafana/aegis-ai-overview-dashboard.json` manually
  (Dashboards → Import) and point it at the Prometheus data source.

The `api` service runs `alembic upgrade head` automatically on startup.
The `worker` service processes uploaded documents (text extraction,
chunking, and embedding) in the background — it must be running for
uploads to move past `status: pending`, and for chat retrieval to have
anything to find.

### Option B — Run services individually

**Backend**
```bash
cd apps/api
python -m venv .venv && source .venv/bin/activate
pip install -e ../../packages/ai   # shared embeddings/vector-store/LLM code
pip install -r requirements.txt
cp .env.example .env  # set JWT_SECRET_KEY, point DATABASE_URL at your Postgres
alembic upgrade head
uvicorn app.main:app --reload
```

**Frontend**
```bash
cd apps/web
npm install
cp .env.example .env.local
npm run dev
```

**Worker**
```bash
cd apps/api  # worker imports the same app package
celery -A ../worker/celery_app.celery_app worker --loglevel=info
```

### Running tests

```bash
cd apps/api
pytest tests/ -v
```

Tests run against an in-memory SQLite database — no external services
required.

## API overview

All routes are versioned under `/api/v1`.

| Endpoint | Method | Auth | Description |
|---|---|---|---|
| `/api/v1/auth/register` | POST | — | Create account |
| `/api/v1/auth/login` | POST | — | Get access/refresh tokens |
| `/api/v1/auth/refresh` | POST | — | Rotate access token |
| `/api/v1/auth/verify-email` | POST | — | Verify email via token |
| `/api/v1/auth/forgot-password` | POST | — | Request reset token |
| `/api/v1/auth/reset-password` | POST | — | Reset password via token |
| `/api/v1/users/me` | GET / PATCH | Bearer | Current user profile |
| `/api/v1/organizations` | GET / POST | Bearer | List / create organizations |
| `/api/v1/organizations/{org_id}/invites` | POST | Bearer (owner/admin) | Invite a member |
| `/api/v1/organizations/invites/accept` | POST | Bearer | Accept an invite |
| `/api/v1/organizations/{org_id}/documents` | GET / POST | Bearer | List / upload documents |
| `/api/v1/organizations/{org_id}/documents/{id}` | GET | Bearer | Document detail + latest version |
| `/api/v1/organizations/{org_id}/documents/{id}` | DELETE | Bearer (owner/admin) | Soft delete |
| `/api/v1/organizations/{org_id}/documents/{id}/versions` | GET / POST | Bearer | List versions / upload new version |
| `/api/v1/organizations/{org_id}/documents/{id}/chunks` | GET | Bearer | Chunks of the latest version |
| `/api/v1/organizations/{org_id}/chat/conversations` | GET / POST | Bearer | List / create conversations |
| `/api/v1/organizations/{org_id}/chat/conversations/{id}/messages` | GET / POST | Bearer | List history / send a message (RAG) |
| `/api/v1/agents` | GET | — | List available agents (platform-wide) |
| `/api/v1/organizations/{org_id}/agents/invoke` | POST | Bearer | Ad-hoc agent invocation (no conversation) |
| `/api/v1/organizations/{org_id}/agents/runs` | GET | Bearer | Agent invocation history |
| `/api/v1/organizations/{org_id}/tickets` | GET / POST | Bearer | List / create tickets |
| `/api/v1/organizations/{org_id}/tickets/{id}` | GET / PATCH | Bearer | Get ticket / update status, priority, assignment |
| `/api/v1/organizations/{org_id}/audit-logs` | GET | Bearer (owner/admin) | List audit log entries for the org |
| `/api/v1/organizations/{org_id}/analytics/overview` | GET | Bearer | Document/chat/ticket/agent-run counts + AI cost estimate |
| `/metrics` | GET | — | Prometheus scrape endpoint |
| `/health` | GET | — | Health check |

Full interactive docs at `/api/docs` when `ENVIRONMENT != production`.

## Milestone 6 completion verification

- Backend: `DEBUG=false JWT_SECRET_KEY=test-secret python3.12 -m pytest tests/ -q` → `95 passed`
- Frontend: `npm run build` ✅ and `npm run lint` ✅
- Docker compose config: YAML validation pass
