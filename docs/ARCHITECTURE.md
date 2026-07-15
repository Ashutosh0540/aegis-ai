# Architecture — Milestone 1

## Style

AegisAI is a **modular monolith** following **Domain-Driven Design** and
**Clean Architecture**. It is deployed as a single API service (plus a
worker process and a frontend), but internally organized into bounded
contexts under `apps/api/app/modules/`.

## Why modular monolith, not microservices

- One deployable unit — no service mesh, no distributed tracing overhead,
  no network calls between what are really tightly-coupled domains at this
  stage of the product.
- Module boundaries are enforced by code convention (service-layer calls
  only, no cross-module ORM queries) rather than network boundaries — this
  keeps the option to extract a module into its own service later without
  a rewrite, once there's an actual scaling or team-ownership reason to.

## Module layout

Each module under `app/modules/<name>/` follows the same four-file shape:

| File | Responsibility |
|---|---|
| `models.py` | SQLAlchemy ORM — persistence only |
| `schemas.py` | Pydantic v2 — the wire contract, never the ORM object |
| `service.py` | Business logic — framework-agnostic, unit-testable without HTTP |
| `router.py` | FastAPI routes — thin, delegates to `service.py` via DI |

Modules implemented in Milestone 1:

- **`auth`** — registration, login, JWT issuance/refresh, email verification
  tokens, password reset tokens.
- **`users`** — user identity and profile.
- **`organizations`** — multi-tenancy: organizations, membership, roles,
  invites.

## Multi-tenancy & RBAC

- `Organization` is the tenant boundary. Every future module that stores
  tenant data (documents, chats, workflows) will carry an `organization_id`
  foreign key.
- `OrganizationMember` is a join table (not an array column) carrying
  `role` (`owner` / `admin` / `member`), so we can extend it later without
  a schema rewrite.
- `RequireOrgRole` (`app/core/deps.py`) is a FastAPI dependency factory:
  `Depends(RequireOrgRole("owner", "admin"))` enforces that the caller
  holds one of the given roles in the org referenced by the `org_id` path
  parameter, on any route in any module.

## Auth design

- Passwords hashed with bcrypt via passlib.
- JWT access tokens (short-lived, 30 min default) + refresh tokens
  (7 days default), both signed with `JWT_SECRET_KEY` from the environment.
- Email verification and password reset use single-use, expiring tokens
  stored in `auth_tokens` — decoupled from the JWT flow entirely, so a
  leaked verification link can't be used as a session token.
- `get_current_user` (`app/core/deps.py`) is the single place that parses
  and validates a bearer token; every protected route across every module
  depends on it, so auth behavior is identical platform-wide.

## Database conventions (enforced by mixins in `app/core/models_mixins.py`)

- UUID v4 primary keys, generated application-side.
- `created_at` / `updated_at`, UTC, auto-managed.
- Soft delete via nullable `deleted_at` — queries must explicitly filter
  `deleted_at.is_(None)`; there's no automatic global filter, to keep the
  ORM layer simple and avoid "invisible" query rewriting.

## What's intentionally deferred

- Email delivery (SMTP/notification service) — verification and reset
  tokens are created and returned to the caller/router today; the router
  has a `TODO` marking where dispatch will be wired once the
  notification/email agent exists (Milestone 5).
- OAuth2 login (Google) — config fields exist in `Settings` but the
  provider flow itself lands alongside a broader auth hardening pass.
- Pinecone / FAISS, LangChain, LangGraph, n8n — Milestones 3–5.

---

# Architecture — Milestone 2 (Documents)

## New module: `documents`

Same four-file shape as `auth`/`users`/`organizations`, plus two extra
pieces specific to file handling:

- **`storage.py`** — a `StorageBackend` protocol with an S3-compatible
  implementation (`S3StorageBackend`, via boto3). It talks to MinIO in
  development and can point at real AWS S3 in production without a code
  change — both speak the S3 API. Routes/services depend on the protocol,
  never on boto3 directly.
- **`extraction.py`** — pure functions: `extract_text(content_type, bytes)`
  and `chunk_text(text)`. No DB, no FastAPI, no Celery — unit tested with
  plain bytes in, strings out.
- **`processing.py`** — `process_document_version_sync(db, storage,
  version_id)`, the actual processing logic, written against a plain sync
  SQLAlchemy `Session`. This is the function both the Celery task and the
  test suite call directly.
- **`tasks.py`** — the Celery task itself is a thin wrapper: open a sync
  session + storage backend, call `process_document_version_sync`, close
  the session. All the logic lives in `processing.py` so it's testable
  without a Celery broker.

## Why versioning is a separate table

`Document` is the stable identity; `DocumentVersion` is an immutable
snapshot (own `storage_key`, `checksum_sha256`, processing `status`).
Re-uploading a file creates version N+1 — it never overwrites version N's
row or its chunks. This means a citation generated in Milestone 3+ can
always point at the exact version it came from, even after someone
uploads a newer copy of the same document.

## Why processing is async (Celery), not inline in the request

PDF/DOCX parsing can take seconds on large files. Upload returns
immediately with the version in `status: pending`; the Celery worker picks
it up, extracts text, chunks it, and flips status to `completed` /
`failed` / `needs_ocr`. The frontend polls `GET .../documents/{id}` while
any version is `pending`/`processing`.

## Why a sync engine exists alongside the async one

FastAPI request handlers use the async SQLAlchemy engine (`app/core/
database.py::engine`). Celery tasks run as plain synchronous Python — no
event loop — so they use a separate sync engine (`sync_engine` /
`SyncSessionLocal`, same file) pointed at the same database via psycopg2
instead of asyncpg. This is a standard pattern for async web apps with a
Celery worker and avoids forcing an event loop into every task.

## OCR readiness

`extract_text` dispatches by content type. A PDF that yields empty text
(almost always a scanned image, not real text) is detected and the
version is marked `needs_ocr` rather than silently completing with zero
chunks. The actual OCR call is a documented stub — none of the required
upload formats mandate OCR yet, but the seam exists for when scanned-
document support becomes a priority.

## What's intentionally deferred (Milestone 2)

- The `embedding` column on `DocumentChunk` exists (nullable JSON) but is
  populated in Milestone 3 — this avoids a schema rewrite when embeddings
  land, only an `ALTER`/backfill.
- Actual OCR execution (pytesseract or equivalent).
- Presigned/download URLs for raw files — chunks are queryable via the API
  today; serving the original file back to the frontend is deferred until
  there's a concrete need (e.g. citation "view original" in Milestone 3+).

---

# Architecture — Milestone 3 (RAG)

## New shared package: `packages/ai`

Unlike `auth`/`documents`/`chat`, the embedding, vector store, and LLM
code isn't API-specific — the worker needs it too (to embed chunks right
after chunking them). It lives in `packages/ai/aegis_ai_core`, installed
editable into both the `api` and `worker` images, so there's exactly one
copy of this logic rather than two that can drift.

Three protocols, each with a real (production) and fake (test)
implementation — the same pattern used for `StorageBackend` in
Milestone 2:

| Protocol | Production | Test |
|---|---|---|
| `EmbeddingProvider` | `HuggingFaceEmbeddingProvider` (local sentence-transformers) | `FakeEmbeddingProvider` (deterministic hash-based) |
| `VectorStoreBackend` | `PineconeVectorStore` (production, namespaced per org) | `FAISSVectorStore` (same class used in dev *and* tests — real, not faked) |
| `LLMProvider` | `OllamaLLMProvider` (local Llama 3 via HTTP) | `FakeLLMProvider` (deterministic canned response) |

**Why FAISS isn't faked in tests, but embeddings and the LLM are:** FAISS
is a pure local library — no network, no API key, no model download. The
test suite uses the real `FAISSVectorStore` against a temp directory, so
retrieval ranking is genuinely exercised (see
`tests/test_ai_core.py::test_faiss_vector_store_upsert_and_query_ranks_by_similarity`).
HuggingFace model downloads and a running Ollama server both require
network access this environment doesn't have, so those two stay faked —
same honest limitation as MinIO in Milestone 2.

**Why `FAISSVectorStore` uses `IndexIDMap2` over a flat index:** FAISS's
plain `IndexFlatIP` has no concept of "delete this vector" or "here's an
opaque ID for it" — `IndexIDMap2` adds both, mapping each chunk's UUID to
a deterministic int64 id so upserts and deletes work by chunk id rather
than by array position (which would shift on every delete).

**Why a namespace-per-org design for Pinecone, and an index-per-org design
for FAISS:** both achieve the same tenant isolation guarantee (a query for
org A can never return org B's vectors) using each backend's native
mechanism — Pinecone namespaces are built for exactly this; FAISS has no
native multi-tenancy concept, so a separate index file per org is the
simplest correct equivalent.

## Embedding generation: extended in the worker, not a new task

`process_document_version_sync` (Milestone 2) now takes an
`EmbeddingProvider` and `VectorStoreBackend` alongside the existing
`storage` argument. Right after chunks are created (same DB transaction
scope), each chunk's text is embedded and upserted into the vector store
with metadata (`document_id`, `document_version_id`, `chunk_index`,
`filename`) — this is what a later citation renders back to the user. The
`DocumentChunk.embedding` column (added as nullable JSON in Milestone 2)
is now actually populated, not just reserved.

## New module: `chat`

Same four-file shape as every other module. `Conversation` holds an
optional `document_id` — if set, retrieval is restricted to that one
document (`vector_store.query(..., document_id=...)`); if unset,
retrieval spans the whole organization's knowledge base.

`ChatMessage.citations` is a JSON list of `{chunk_id, document_id,
document_version_id, chunk_index, filename, score}` — built directly from
the vector store matches used in that turn's prompt, not inferred from
the LLM's output. This is what lets the frontend show "Source:
handbook.pdf" under an answer with confidence, rather than the LLM
possibly hallucinating a source it wasn't actually given.

## Why this is a single-pass chain, not an agent (yet)

`post_message` does exactly one retrieve-then-generate pass per turn:
embed → query → build prompt (`aegis_ai_core.prompts`, the actual
LangChain `PromptTemplate` usage) → call the LLM once → store. There's no
loop where the model decides to search again, call a tool, or reason
across multiple steps — that's explicitly LangGraph's job, and LangGraph
doesn't appear until Milestone 4 (Supervisor Agent, Knowledge Agent).
Keeping Milestone 3 a plain chain keeps that boundary clean: Milestone 4
wraps *this* retrieval logic in a graph rather than replacing it.

## What's intentionally deferred (Milestone 3)

- LangGraph, Supervisor Agent, Knowledge Agent, Email Agent, Meeting
  Agent, Analytics Agent, Workflow Agent — Milestone 4.
- Streaming responses (today's `/messages` POST is request/response, not
  SSE/websocket) — revisit once the frontend chat UI needs it.
- Re-ranking retrieved chunks with a cross-encoder — top-k cosine
  similarity only for now.
- Deleting a document's vectors when the document itself is soft-deleted
  — `DocumentChunk` rows are retained (soft-delete-consistent with
  everything else), but the corresponding vector store entries aren't
  proactively removed yet.

---

# Architecture — Milestone 4 (LangGraph agents)

## `aegis_ai_core.agents`: Supervisor → Knowledge Agent

The graph lives in the shared package (same reasoning as embeddings/vector
store/LLM in Milestone 3 — the worker doesn't need it, but keeping all AI
orchestration code in one place avoids a second home for "AI logic"
splitting attention between `packages/ai` and `apps/api`).

```
supervisor (routes) → knowledge_agent (retrieve + generate) → END
```

**Why the supervisor is a real node and not just a hardcoded edge:**
today there's exactly one destination, so a hardcoded edge would produce
identical behavior. But `state["route"]` is written by an actual function
that inspects the request — Milestone 5 changes that function's body (real
classification: "does this look like an email request, a scheduling
request, or a document question?") without touching the graph's shape,
the calling code in `chat/service.py`, or the `agents` module's API. The
seam is where it needs to be now, not retrofitted later.

**Why zero retrieval matches short-circuits before calling the LLM:**
sending an empty-context prompt to an LLM and hoping it says "I don't
know" is unreliable — models often confabulate an answer anyway. The
`knowledge_agent` node checks `matches` before building a prompt at all,
so "no relevant documents" is a deterministic code path, not something
left to the model's judgment.

## `chat` module: same contract, new internals

`chat.service.post_message` used to call `embed → query → build_rag_prompt
→ generate` directly (Milestone 3). It now calls
`aegis_ai_core.agents.run_supervisor_graph(...)` and reads `answer` /
`citations` off the returned state — the function signature, the
`ChatMessage` shape, and every existing test in `test_chat.py` are
unchanged. This is the "modules communicate through service interfaces"
principle in practice: swapping what's behind `post_message` didn't
require touching the `chat` router, schemas, or the frontend.

## New module: `agents`

- `GET /api/v1/agents` — static registry (`AVAILABLE_AGENTS` from
  `aegis_ai_core.agents`), not org-scoped since it's platform capability
  info, not tenant data.
- `POST /organizations/{org_id}/agents/invoke` — runs the graph outside of
  a chat conversation (no history, one-shot), for programmatic/API access
  or future non-chat integrations (e.g. a workflow step in Milestone 5
  that needs a knowledge-agent answer without a conversation attached).
- `GET /organizations/{org_id}/agents/runs` — the `AgentRun` audit trail:
  which agent, which route, latency, status, and (on failure) the error
  message. Deliberately minimal — this is the seed Milestone 6's full
  audit log and analytics dashboard build on, not a finished feature.

**Why a failed run returns 201 with `status: "error"` rather than a 500:**
the whole point of `AgentRun` is to make agent behavior inspectable. If an
error just produced an opaque 500, the record of what was attempted and
why it failed would be lost. `invoke_agent` catches the exception, records
a run with `status: "error"` and `error_message` set, and returns that
run — the client sees exactly what happened rather than a generic failure.

## What's intentionally deferred (Milestone 4)

- Email Agent, Meeting Agent, Analytics Agent, Workflow Agent — Milestone
  5 (Workflow Automation) adds these as new branches off the supervisor's
  routing function.
- Real LLM-based intent classification in the supervisor node — today's
  fixed routing is correct given only one destination exists; becomes a
  real decision once there's more than one place to route to.
- LangSmith tracing of graph execution — mentioned in the tech stack's
  monitoring section, wired up alongside Prometheus/Grafana in
  Milestone 6.
- Multi-turn tool use within a single agent turn (the graph currently
  does one retrieval pass per message, not an iterative "retrieve, check
  if sufficient, retrieve again" loop).

---

# Architecture — Milestone 5 (Workflow Automation)

## Two new cross-cutting providers in `app/core`

Unlike embeddings/vector store/LLM (Milestone 3, in `packages/ai` because
the worker needs them too), notifications and n8n are API-only concerns —
they live in `app/core` alongside `security.py`/`database.py`, following
the same protocol-with-real-and-fake-implementations pattern established
throughout this project:

| Protocol | Production | Dev default | Test |
|---|---|---|---|
| `EmailProvider` | `SMTPEmailProvider` | `ConsoleEmailProvider` (logs instead of sending — not a placeholder, a legitimate no-SMTP-configured default) | `FakeEmailProvider` |
| `N8nClient` | `HttpN8nClient` | *(same — talks to a local n8n container)* | `FakeN8nClient` |

**Why `HttpN8nClient.trigger_webhook` returns `False` instead of raising:**
tested for real in this environment (an unreachable host genuinely
exercises the `except httpx.HTTPError` path) — a workflow automation
outage must never fail the ticket-creation request that triggered it. The
caller doesn't need to handle an exception; it gets a boolean it can log
or ignore.

## Closing Milestone 1's TODO

`auth.service.register_user` and `create_password_reset_token` now take
an `EmailProvider` and actually call `send_email(...)` with a real
verification/reset link built from `FRONTEND_BASE_URL`. This is a
signature change, not a redesign — the router now injects
`Depends(get_notification_provider)` and passes it through, same pattern
as `storage`/`embedding_provider` elsewhere.

## New module: `workflows` (Tickets)

`Ticket` is deliberately simple — title, description, status, priority,
`assigned_to_id`, and a `source` field (`manual` vs `agent`) that records
*how* a ticket came to exist, which matters once the dashboard needs to
distinguish "a person filed this" from "the Workflow Agent inferred this
from a chat message." `create_ticket` is the single path both a direct
`POST /tickets` call and `create_ticket_from_agent_draft` (used by the
graph's workflow_agent route) go through — the agent path isn't a special
case with different validation or a skipped n8n trigger.

## Supervisor's routing becomes real

Per Milestone 4's design note ("Milestone 5 adds branches without
restructuring the graph"), `_supervisor_node` now does genuine
keyword-based classification across three destinations
(`knowledge_agent`, `workflow_agent`, `email_agent`) instead of the fixed
single-destination rule from Milestone 4. The graph's shape — one
supervisor node, conditional edges to specialized agents, each agent
edging to `END` — didn't change; only the routing function's body and the
node registry did.

## "Graph decides, service acts" — now with two real actions

Milestone 4 established this boundary for the (then hypothetical)
non-knowledge routes; Milestone 5 is where it's actually exercised:

- `workflow_agent` node returns `ticket_draft` (title/description/priority)
  — never touches the database.
- `email_agent` node returns `email_draft` (to/subject/body, `to` parsed
  via a simple regex against the request text) — never calls
  `EmailProvider` itself.
- `app/core/agent_side_effects.py::apply_agent_side_effects` is the one
  place that turns either draft into a real action (`Ticket` row + n8n
  webhook, or an actual `send_email` call). Both `chat.service.
  post_message` and `agents.service.invoke_agent` call this same
  function, so a "there's a bug in checkout" message produces the exact
  same ticket whether it arrives via a chat conversation or the ad-hoc
  `/agents/invoke` endpoint.

**Why the email agent only sends when a recipient is parseable:**
guessing a recipient (e.g. defaulting to the requester) risks sending
mail to the wrong person or the requester themselves. If
`EMAIL_ADDRESS_PATTERN` finds no match in the request text, the node
returns a draft with `to: null` and the answer says so explicitly — the
person gets the drafted text to review and send however they'd like,
rather than the system silently doing nothing or guessing wrong.

## Frontend: `/dashboard/tickets`

Same shape as the documents/chat pages — org picker, a create form,
a list with inline status updates. The `source` column visibly
distinguishes agent-created tickets (🤖) from manually filed ones, so
users can see the Workflow Agent's output isn't hidden from them.

## What's intentionally deferred (Milestone 5)

- Meeting Agent, Analytics Agent — not in this milestone's scope per the
  frozen spec (Milestone 4 was Supervisor + Knowledge; Milestone 5 was
  Workflow Automation specifically).
- Ticket assignment notifications (an `assigned_to_id` change doesn't
  currently trigger an n8n webhook or email — only creation does).
  Straightforward to add via the same `n8n_client.trigger_webhook`
  call in `update_ticket` once there's a concrete need.
- LLM-based email drafting quality — `FakeLLMProvider` in tests, and the
  real `OllamaLLMProvider` in production, both just answer a single
  prompt; there's no review/revision loop.
- Actually invoking n8n workflows *shipped* in `workflows/n8n/` requires
  a person to import them into a running n8n instance and configure real
  notification credentials (Slack, PagerDuty, etc.) — the JSON in this
  repo is a working starting point, not something wired up automatically.

## Milestone 6: Analytics, audit, monitoring, production readiness

### New module: `audit`

`AuditLog` (UUID PK, org-scoped, soft-delete/timestamp mixins like every
other table) records both explicit security/AI events
(`auth.login_succeeded`/`auth.login_failed`, chat/agent AI actions) and,
via `AuditRequestMiddleware`, a best-effort row for every API request
(method/path/status/latency/user/org/IP). The middleware sits outside
FastAPI's `Depends()` system, so it can't use `app.dependency_overrides`
the way every other module's DB access does in tests — it reads its
session factory from `request.app.state.audit_session_factory` instead
(defaults to the real `AsyncSessionLocal` in `main.py`, swapped per-test
in `conftest.py`). This state-based override is a new pattern, worth
reusing for any future middleware that needs DB access.

Login audit events have `organization_id = None` (login happens before
org context exists), so they don't appear under the org-scoped
`GET /organizations/{org_id}/audit-logs` endpoint — verified directly
against the DB in tests instead. If a future dashboard needs login events
per-org, that requires querying by org *membership* at read time, not by
a stored `org_id` column.

### New module: `analytics`

Deliberately has no `models.py` — it's read-only aggregation over
existing tables (documents, chat messages, tickets, agent runs), not a
new source of truth, so the usual four-file shape collapses to three
files. `GET /organizations/{org_id}/analytics/overview` returns those
counts plus an AI cost figure that's explicitly a placeholder
(`Settings.AI_COST_PER_AGENT_RUN_USD` × agent-run count) since Ollama's
API doesn't expose token-level usage the way hosted-model APIs do; real
per-token costing needs usage metering that doesn't exist yet.

### LangSmith tracing

`app/core/tracing.py::configure_langsmith()` copies
`Settings.LANGCHAIN_*` into process env vars at startup (`main.py` and
`celery_app.py`) — LangChain/LangGraph read tracing config from the
environment, not an explicit API, so this is the only integration point
needed. `OllamaLLMProvider.generate` is wrapped with `@traceable` and
`run_supervisor_graph` passes `run_name`/`tags`/`metadata` via
`graph.invoke(..., config=...)`. Genuinely a no-op with zero network
calls when `LANGCHAIN_TRACING_V2` is false (the default) — this sandbox
has no LangSmith access, so tests run with tracing off.

### Prometheus metrics

`app/core/metrics.py::PrometheusMiddleware` is a sibling to
`AuditRequestMiddleware` rather than a merge into it: audit rows are
business/security records read through a normal org-scoped endpoint;
Prometheus metrics are process-level counters/histograms scraped over
HTTP by an external system. Same per-request timing shape, different
storage model and consumer — two small middlewares stay clearer than one
middleware serving two concerns.

`GET /metrics` (unauthenticated, standard for Prometheus scrape
endpoints — access is normally controlled at the network layer, not app
auth) exports `http_requests_total{method,path,status_code}` (Counter)
and `http_request_duration_seconds{method,path}` (Histogram). The `path`
label uses the matched **route template** (`/organizations/{org_id}/...`),
read from `request.scope["route"]` after `call_next` returns — using the
raw request path would let UUIDs in URLs explode metric cardinality.
Metrics live on a dedicated `CollectorRegistry` (not the global default)
so re-importing `app.main` across test modules doesn't hit
`prometheus_client`'s duplicate-timeseries error.

### Grafana + Prometheus (docker-compose)

`docker/prometheus/prometheus.yml` is a minimal scrape config pointed at
`api:8000/metrics` (15s interval) — a working local/dev starting point,
not a production topology (a real deployment usually runs Prometheus
outside this compose file entirely). `grafana` and `prometheus` are new
compose services; Grafana's host port is `3001` since `apps/web` already
owns host port `3000`. `workflows/grafana/aegis-ai-overview-dashboard.json`
is a starter dashboard (request rate, 5xx rate, p95 latency, and a total-
requests stat panel, all by path) — like `workflows/n8n/*.json`, it's
meant to be imported manually via the Grafana UI (Dashboards → Import),
not auto-provisioned.

### What's intentionally deferred (Milestone 6)

- Alerting rules (Prometheus Alertmanager / Grafana alert rules) — the
  starter dashboard is observational only; no on-call paging is wired up.
- Auth on `/metrics` — acceptable for this repo's scope (network-level
  access control is the normal pattern for scrape endpoints), but a
  hardened production deployment behind a shared ingress might want an
  allowlist or a separate internal-only listener.
- Structured/JSON application logging — `main.py`'s catch-all exception
  handler still just returns a generic 500 body; nothing here ships
  correlated request-id logging beyond what the audit trail already
  captures per request.
- **Verification status**: this sandbox session had no network access to
  install `prometheus-client` or any other project dependency (confirmed
  directly — `pip install` and `curl` to PyPI were both blocked), so the
  code above was written to match existing patterns and reviewed by hand
  but **could not be executed or test-verified in this session**. See
  `PROJECT_STATE.md` for the exact, honest status and what the next
  session needs to do first.
