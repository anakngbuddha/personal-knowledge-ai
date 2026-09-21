# Build Status

Plan of record: **`Project_Plan.md`** (Rev 4, 2026-09-20).

## Phase Status against Project_Plan.md (Rev 4)

| Phase | Name | State | Notes |
|---|---|---|---|
| 0 | Security Foundation & PostgreSQL RLS | **Done** | Cryptographic JWT auth, PostgreSQL RLS, audit log, session injection, CI isolation tests |
| 1 | Ingestion Pipeline | **Done** | Multi-format upload, queue, SSRF-safe fetcher, metadata gate |
| 2 | Hybrid Retrieval | **Done** | pgvector + FTS with RRF fusion and permission filters |
| 3 | Grounded Answers | **Done** | Grounded generation, citations, refusal, conversations |
| 4 | Product Catalog & Typed Graph | **Done** | Product catalog, typed edges, cycle/conflict detection, impact queries |
| 4.5 | Evaluation Substrate | **Done** | 54-question set and written baselines |
| 5 | Tool Calling, Durable Runner, HITL | **Done** | Python tools, PostgreSQL DAG queue, approval state and audit |
| 6 | RFP Responder | **Done** | Spreadsheet to cited answers, HITL, DOCX |
| 6.5 | Golden Scenarios | **Done** | 20-scenario regression suite |
| 7 | Workflow Workspace UI | **Done** | Gallery, task tree, review modal, downloads |
| 8 | Solution Composer & Post-Sales Playbooks | **Done** | Discovery-to-HLD/BOM with graph validation, incident triage, upgrade impact audit |
| 9 | MCP Client | **Done** | Playwright, Microsoft 365 Graph, and Brave Search via allowlisted MCP tools |
| 10 | Notes, Freshness & Enterprise Hardening | **Done** | Wikilinked tribal notes, vendor URL hash watches, OIDC/SAML SSO, restore drills |

## Phase 8 Endpoints

| Method | Path | Purpose |
|---|---|---|
| POST | `/workflows/solution-composer/run` | Extract discovery constraints, compose a conflict-free bundle, produce HLD/BOM, pause for approval |
| POST | `/workflows/incident-triage/run` | Analyze logs as untrusted data, traverse the install graph, retrieve evidence, export a runbook |
| POST | `/workflows/upgrade-impact/run` | Compute transitive prerequisites, breaking impacts, integrations, and alternatives |
| GET | `/workflows/runs/{id}/deliverable` | Download the completed Phase 6 or Phase 8 DOCX |

## Phase 9 Endpoints

| Method | Path | Purpose |
|---|---|---|
| GET | `/integrations/mcp` | List Playwright, Microsoft 365, and Brave Search status for the caller’s org |
| GET | `/integrations/mcp/{id}` | Fetch one integration; cross-tenant ids are 404 |
| PUT | `/integrations/mcp/{server_slug}` | Admin enablement, host allowlist, encrypted secret upsert |
| POST | `/integrations/mcp/{server_slug}/test` | `list_tools` ping against the configured server |

## Phase 10 Endpoints

| Method | Path | Purpose |
|---|---|---|
| GET/POST | `/notes` | List and create SE tribal notes (paginated) |
| GET/PUT/DELETE | `/notes/{id}` | Read, update, or delete a note; wikilinks re-extracted on save |
| GET | `/notes/by-link/{kind}/{ref}` | Backlinks from notes to a product, account, or note |
| GET/POST | `/freshness/sources` | Register and list upstream vendor URLs |
| POST | `/freshness/sources/{id}/check` | Fetch now; a hash change raises a staleness alert |
| GET | `/freshness/alerts` | Open (unacknowledged) staleness alerts |
| POST | `/freshness/alerts/{id}/ack` | Acknowledge an alert after the new collateral is ingested |
| GET/POST | `/ops/restore-drills` | Admin list / run a logical dump→restore drill against SLA |
| GET | `/ops/sso` | OIDC/SAML configuration status (no secrets) |
| PUT | `/ops/sso/{protocol}` | Admin upsert of issuer, audience, encrypted client secret |
| POST | `/auth/oidc/callback` | Exchange a validated OIDC ID token for a local JWT |
| POST | `/auth/saml/acs` | Exchange a signed SAML assertion for a local JWT |
