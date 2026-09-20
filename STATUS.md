# Build Status

Plan of record: **`Project_Plan.md`** (Rev 4, 2026-09-20).

---

## Phase Status against Project_Plan.md (Rev 4)

| Phase | Name | State | Notes |
|---|---|---|---|
| 0 | Security Foundation & PostgreSQL RLS | **Immediate Priority** | Must replace dev header spoofing with JWT, implement real PostgreSQL RLS policies, audit log, and CI isolation tests |
| 1 | Ingestion Pipeline | **Done** | Multi-format bulk upload, background queue, SSRF-safe URL fetcher, metadata approval gate |
| 2 | Hybrid Retrieval | **Done\*** | Hybrid vector + FTS with RRF fusion, permission & metadata filters (eval baseline pending in Phase 4.5) |
| 3 | Grounded Answers | **Done\*** | Grounded answer generation, citations, refusal on missing context, multi-turn conversations |
| 4 | Product Catalog & Typed Graph | **Done** | Product catalog (own/resold), capability taxonomy, cycle/contradiction detection, impact queries (see `docs/PHASE4.md`) |
| 4.5| Evaluation Substrate | **Next** | 50-question labeled set, written retrieval & generation baseline |
| 5a | Single-Turn Tool Calling in LLM | Planned | Add tool-calling loop to `LLMProvider`; wrap catalog & retrieval tools |
| 5b | Durable Queue-Based Task Runner | Planned | `task_executions` table with dependency-aware `claim()` via `SKIP LOCKED` |
| 5c | Human-in-the-Loop (HITL) Status | Planned | `waiting_approval` status, resume `UPDATE` endpoint, and audit trail |
| 6 | RFP Responder Playbook | Planned | Spreadsheet ingestion $\rightarrow$ requirement mapping $\rightarrow$ cited drafting $\rightarrow$ HITL $\rightarrow$ DOCX export |
| 6.5| Golden Scenario Evaluation Set | Planned | 20 real past RFPs scored against known-good solutions |
| 7 | Workflow Workspace UI | Planned | Visual task tree, step logs, HITL decision modal |
| 8-10| Advanced Playbooks & Hardening | Planned | Solution Composer, post-sales runbooks, MCP (when justified), freshness |

---

## Implemented Endpoints

| Method | Path | Purpose |
|---|---|---|
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
| POST | `/ask` | Grounded answer generation (sync or SSE streaming) with structured citations |
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
