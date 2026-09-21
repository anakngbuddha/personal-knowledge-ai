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
| 9-10 | MCP & Enterprise Hardening | Planned | External MCP, freshness, notes, recovery drills |

## Phase 8 Endpoints

| Method | Path | Purpose |
|---|---|---|
| POST | `/workflows/solution-composer/run` | Extract discovery constraints, compose a conflict-free bundle, produce HLD/BOM, pause for approval |
| POST | `/workflows/incident-triage/run` | Analyze logs as untrusted data, traverse the install graph, retrieve evidence, export a runbook |
| POST | `/workflows/upgrade-impact/run` | Compute transitive prerequisites, breaking impacts, integrations, and alternatives |
| GET | `/workflows/runs/{id}/deliverable` | Download the completed Phase 6 or Phase 8 DOCX |
