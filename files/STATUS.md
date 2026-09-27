# Build Status: capability inventory

Last updated: 2026-09-27. Replaces the old phase checklist, which marked shipped work as "not started".
**Implemented** = route + service + tests exist. **Partial** = exists with a known gap. **Proposed** = not established in code.
Forward plan: [ROADMAP.md](ROADMAP.md).

| Capability | State | Backed by |
|---|---|---|
| JWT auth, orgs, memberships, roles | Implemented | `app/api/routes/auth.py`, `app/security/deps.py` (membership re-checked every request) |
| PostgreSQL row-level security | Partial | Migration `0022_row_level_security`, `app/db/session.py`, `app/db/rls.py`. Unscoped sessions bypass unless `RLS_DEFAULT_DENY=true`; deploy role must not be superuser/BYPASSRLS (`RLS_REQUIRED=true` enforces) |
| Audit log | Implemented | `app/security/audit.py` |
| Document ingestion (upload, URL, OCR, archives, malware heuristics) | Implemented | `app/api/routes/documents.py`, `app/documents/`, `app/ocr/`, `app/net/ssrf.py` |
| Durable ingestion queue with renewable leases | Implemented | `app/jobs/queue.py`, `app/jobs/lease.py` |
| Hybrid retrieval (pgvector + FTS + RRF), permission predicates | Implemented | `app/api/routes/search.py`, `app/retrieval/` |
| Grounded answers, conversations, streaming | Implemented | `app/api/routes/ask.py`, `app/generation/` (strict by default, claim-support scores) |
| Tool-enabled answers | Partial | `enable_tools=true` works but is not token-streamed |
| Evaluation | Partial | Plumbing checks with fake providers only. No live Gemini/Postgres baseline recorded yet |
| Notes, wikilinks, backlinks | Implemented | `app/api/routes/notes.py`, `app/notes/` |
| Notebooks / source toggling | Implemented | `app/api/routes/notebooks.py` |
| Studio outputs (briefing, FAQ, compare) | Implemented | `app/api/routes/studio.py` |
| Product catalog + typed graph, import, map editing, graph review | Implemented | `catalog.py`, `catalog_import.py`, `map_edit.py`, `graph_review.py` |
| Advisor / customer brief | Implemented | `app/api/routes/advisor.py` |
| Workflows with human approval, RFP/playbooks | Implemented | `app/api/routes/workflows.py`, `app/workflows/`, `playbooks/` |
| Solution composer, incident triage, upgrade impact | Implemented | `app/api/routes/phase8.py` |
| Vendor freshness monitoring + crawl | Implemented | `app/api/routes/freshness.py`, `app/freshness/` |
| SSO (OIDC/SAML) | Implemented | `app/sso/` (off by default) |
| MCP client (Brave, Playwright, M365) | Partial | `app/mcp/`; children get a restricted env + private dir; OS sandbox only if `MCP_CHILD_SANDBOX_COMMAND` is set |
| Custom MCP server (SSE + JSON-RPC) | Implemented | `app/api/routes/mcp_server.py`, `app/mcp/custom_server.py` |
| Ops: restore drills, runtime metrics | Implemented | `app/api/routes/ops.py`, `app/api/routes/runtime.py` |
| Transclusion, audio sources/overview, most Phase 9 differentiators | Proposed | Not found in code |

## Deployment notes

- **RLS**: connect as a non-superuser role without BYPASSRLS. The boot log says `row-level security is NOT enforced` otherwise. Set `RLS_REQUIRED=true` once clean.
- **Background work**: ingestion, workflow and freshness threads run in the web process. Measure first with `GET /ops/runtime` (event-loop lag, thread pool, DB pool, Gemini wait by class). Move them to `python scripts/worker.py` with `WORKER_ENABLED=false` on web only when contention is measured.
- **Gemini quota**: `GEMINI_RPM` is shared by OCR, embeddings and chat; interactive calls go first and `GEMINI_INTERACTIVE_RESERVE` slots per minute stay free for them. Raise `GEMINI_RPM` only to the account's confirmed limit.
