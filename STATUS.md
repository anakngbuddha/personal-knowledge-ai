# Build Status

Plan of record: **`Project_Plan.md`** (Rev 4, 2026-09-20).

---

## Phase Status against Project_Plan.md (Rev 4)

| Phase | Name | State | Notes |
|---|---|---|---|
| 0 | Security Foundation & PostgreSQL RLS | **Done** | Cryptographic JWT auth, real PostgreSQL RLS policies (0011 migration), audit log, session injection hook, and CI isolation tests |
| 1 | Ingestion Pipeline | **Done** | Multi-format bulk upload, background queue, SSRF-safe URL fetcher, metadata approval gate |
| 2 | Hybrid Retrieval | **Done** | Hybrid vector + FTS with RRF fusion, permission & metadata filters (eval baseline verified) |
| 3 | Grounded Answers | **Done** | Grounded answer generation, citations, refusal on missing context, multi-turn conversations |
| 4 | Product Catalog & Typed Graph | **Done** | Product catalog (own/resold), capability taxonomy, cycle/contradiction detection, impact queries (see `docs/PHASE4.md`) |
| 4.5| Evaluation Substrate | **Done** | 54-question labeled set, offline runner, written retrieval & generation baselines, 14 eval unit tests |
| 5a | Single-Turn Tool Calling in LLM | **Done** | `enable_tools` on `/ask`; catalog + hybrid-search tools; Gemini/Fake function calling; bounded one-round loop |
| 5b | Durable Queue-Based Task Runner | **Done** | `workflow_runs` + `task_executions` (0012 + RLS), dependency-aware SKIP LOCKED claim, sequential worker |
| 5c | Human-in-the-Loop (HITL) Status | **Done** | `waiting_approval` status, approve/reject endpoints, audit trail, RBAC |
| 6 | RFP Responder Playbook | **Done** | Spreadsheet parse → graph match → retrieve → cited draft → HITL → DOCX export |
| 6.5| Golden Scenario Evaluation Set | **Done** | Placeholder 20-scenario suite vs seed catalog; scorer is catalog-agnostic (20/20 on Fake/seed) |
| 7 | Workflow Workspace UI | **Done** | Playbook gallery, live task tree, HITL review modal, deliverable download |
| 8-10| Advanced Playbooks & Hardening | Planned | Solution Composer, post-sales runbooks, MCP (when justified), freshness |

---

## Implemented Endpoints

| Method | Path | Purpose |
|---|---|---|
| POST | `/auth/token` | Issue signed cryptographic JWT for API access |
| GET | `/auth/me` | Inspect authenticated principal, tenant context, and RBAC permissions |
| GET | `/health`, `/health/dependencies` | Liveness, dependency checks (DB, vector, storage, LLM) |
| POST | `/documents` | Bulk upload (`files[]`), per-file result rows |
| POST | `/documents/url` | URL ingestion through the SSRF-safe fetcher |
| POST | `/documents/paste` | Pasted discovery notes / RFP extracts |
| GET | `/documents` | List documents, filterable by status and `metadata_complete` |
| GET/PATCH/DELETE | `/documents/{id}` | Read, curate metadata, delete |
| POST | `/documents/{id}/approval` | Promotion gate: incomplete metadata cannot be approved |
| POST | `/documents/{id}/process` | Requeue ingestion |
| GET | `/documents/{id}/status` | Document status + its latest job |
| GET | `/documents/{id}/chunks` | Chunks with their citation anchors |
| POST | `/search` | Hybrid retrieval with branch ranks and timings exposed |
| GET | `/jobs`, `/jobs/stats` | Per-job status with lease reaping and jittered backoff |
| POST | `/ask` | Grounded answer generation (sync or SSE); `enable_tools` for catalog/retrieval tools |
| POST | `/conversations` | Create a new conversation thread |
| GET | `/conversations` | List conversation threads (paginated) |
| GET | `/conversations/{id}` | Read conversation thread with message history and sources |
| DELETE | `/conversations/{id}` | Delete conversation thread and cascading messages |
| POST | `/conversations/{id}/ask` | Continue multi-turn conversation with grounded answer |
| GET | `/conversations/{id}/sources` | Inspect retrieved sources and toggle status |
| GET | `/catalog/products` | Filterable list of catalog products (own and resold) |
| GET | `/catalog/products/{id}` | Product details with capabilities and edges |
| GET | `/catalog/capabilities` | Controlled capability taxonomy |
| GET | `/graph/portfolio` | Full portfolio graph representation |
| GET | `/graph/neighborhood/{id}` | Subgraph neighborhood around a product |
| GET | `/graph/query` | Product impact query (prerequisites, conflicts, alternatives) |
| GET | `/graph/coverage` | Product and capability coverage audit report |
| POST | `/graph/suggest-edges` | AI edge suggestion analysis over ingested document chunks |
| POST | `/graph/edges/{id}/approve` | Approve edge suggestion into verified relationship |
| POST | `/graph/edges/{id}/reject` | Reject edge suggestion (with rejection idempotency) |
| GET | `/playbooks` | Gallery catalog of YAML playbooks (fixtures excluded) |
| GET | `/workflows/runs` | Paginated workflow run summaries (task counts, no payloads) |
| GET | `/workflows/runs/{id}` | Run detail with task tree |
| POST | `/workflows/runs/{id}/tasks/{slug}/approve` | HITL approve (unlocks downstream) |
| POST | `/workflows/runs/{id}/tasks/{slug}/reject` | HITL reject (halts the run) |
| POST | `/workflows/rfp/run` | Upload CSV/XLSX and start the RFP responder playbook |
| GET | `/workflows/runs/{id}/deliverable` | Download approved RFP `.docx` |
