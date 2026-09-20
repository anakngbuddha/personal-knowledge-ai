# Project Plan: Solution Engineering Knowledge Workspace & Agentic Operating System

Status: **Rev 3 (2026-09-20)**. Supersedes Rev 2 and `docs/ROADMAP.md`.

Rev 3 incorporates the strategic evolution from a passive RAG/Catalog web application into an **Agentic Operating System and Second Brain** for **Pre-Sales, Post-Sales, and Tech Engineering/Architecture**. The knowledge substrate (Phases 1–4: clean chunking, pgvector hybrid retrieval, citation anchors, and the typed product catalog graph) is now exposed as first-class **Agent Tools** coordinated by a **Task-Graph (DAG) Execution Engine** with declarative **Markdown/YAML Playbooks**, **Model Context Protocol (MCP)** tool harnesses, and stateful **Human-in-the-Loop (HITL)** approval gates.

---

## 0. Decided parameters

| Question | Decision | Consequence |
|---|---|---|
| Deployment model | **Shared multi-tenant** | Row-level security from day one; isolation tests permanent |
| Catalog scope | **Own products and resold third-party products** | `vendor` and `source_of_truth` on every product; vendor collateral freshness is tracked |
| Collateral ownership | **Single owner (you), for now** | Governance stays lightweight: review dates and an audit dashboard, no bloated multi-tier review bureaucracy |
| CRM integration | **Out of scope** | Accounts and opportunities are native records; CSV import/export only |
| Scale, year one | **~20 products, ~50 documents, ~50 users** | Small, dense, high-accuracy bar. Focus on agent precision, graph integrity, and workflow execution over distributed microservices |
| Call recording | **Out of scope** | No audio/video ingestion. Discovery input enters as typed or pasted text, uploaded RFP spreadsheets, or SOW drafts |
| **Agent Execution Model** | **Declarative Task DAG with Human-in-the-Loop (HITL)** | Hierarchical workflows (Workflow $\rightarrow$ Task $\rightarrow$ Subtask) with explicit inputs, outputs, prompts, and tools. Stateful pause at approval gates |
| **Playbooks & Skills Authoring** | **Pure Markdown (`.md`) and YAML (`workflow.yaml`)** | Domain logic, prompt templates, and architecture rules live in the filesystem (`playbooks/`, `skills/`), decoupled from Python backend code |
| **Tool & Context Standard** | **Model Context Protocol (MCP) + Internal Knowledge Tools** | Phase 1–4 capabilities wrapped as internal tools. External tool integration standardized on MCP |
| **Initial MCP Tool Priorities** | **1. Local Filesystem, 2. Web/Fetch, 3. Exporters** | Direct ingestion of customer RFP spreadsheets/Word docs; live vendor doc/release-note retrieval; automated DOCX/Markdown report export |

---

## 1. What this is

A comprehensive **Agentic Second Brain** for pre-sales, post-sales, and solution architects. It unifies product catalogs, technical collateral, compatibility rules, and account history into one typed knowledge substrate, driven by an autonomous workflow orchestrator that executes complex engineering playbooks.

```text
┌─────────────────────────────────────────────────────────────────────────┐
│                          ORCHESTRATION LAYER                            │
│  Playbooks & Skills (.md / .yaml)  │  Agent Harness & MCP Integrations │
│  - RFP Responder Workflow          │  - Local Filesystem MCP           │
│  - Solution Composer (HLD/BOM)     │  - Upstream Web/Fetch MCP         │
│  - Incident Triage Runbook         │  - DOCX / Markdown Exporters      │
├─────────────────────────────────────────────────────────────────────────┤
│                   GRAPH EXECUTION ENGINE (STATEFUL DAG)                 │
│   [Task 1: Intake] ──> [Task 2: Evaluate] ──> [Task 3: Graph Audit]     │
│            │ (Prompts, Tools, State)                  │                 │
│            ▼                                          ▼                 │
│   [Human Gate: Sign-off] <──────────────────── [Task 4: Draft SOW]      │
├─────────────────────────────────────────────────────────────────────────┤
│                KNOWLEDGE SUBSTRATE (Phases 1 - 4 As-Built)              │
│   Hybrid Vector/FTS Search  │  Typed Product Graph  │  Citation Engine  │
└─────────────────────────────────────────────────────────────────────────┘
```

The system handles real-world technical scenarios end-to-end:

> **Pre-Sales RFP Scenario**: An SE uploads an 80-question customer RFP spreadsheet. The engine parses requirements, audits internal capabilities, runs contradiction and prerequisite checks against the product graph, retrieves cited evidence chunks, flags low-confidence gaps, halts at a **Human-in-the-Loop approval gate** for architect review, and exports a branded DOCX response package.
>
> **Architecture & Solution Scenario**: A customer needs cloud infrastructure with on-prem integration and video conferencing. The agent composes compatible product bundles, validates cycle-free prerequisites, verifies that no conflicting products are bundled, produces a bill of materials (BOM), and generates a High-Level Design (HLD) draft.
>
> **Post-Sales Incident Scenario**: An engineer pastes an escalation log. The agent maps the customer's install base, traverses dependency edges to isolate root-cause candidates, queries approved runbooks, and drafts an actionable remediation procedure.

---

## 2. Architectural Comparison

| Capability | Obsidian / Notes App | Traditional RAG Chatbot | Personal Knowledge AI (Rev 3) |
|---|---|---|---|
| **Product Relationships** | Untyped text links | Untyped embeddings | **Typed Directed Graph** (`requires`, `conflicts_with`, `integrates_with`) with evidence |
| **Evidence & Truth** | Manual copy-paste | Unchecked generation | **Grounded Citations** down to page/slide with strict refusal when context is missing |
| **Execution Model** | None | Single-turn Q&A | **Multi-step Task DAG** (Tasks $\rightarrow$ Subtasks $\rightarrow$ Prompts, Tools, Data) |
| **Playbook Customization** | Static text notes | Hardcoded in backend | **Markdown/YAML Playbooks & Skills** in filesystem (`playbooks/`, `skills/`) |
| **Tooling & Integrations** | Community plugins | Hardcoded API endpoints | **Model Context Protocol (MCP)** + Internal Knowledge Tool harness |
| **Governance & Safety** | None | Blind LLM answers | **Stateful Human-in-the-Loop (HITL) Approval Gates** before finalizing output |

---

## 3. Core Principles

1. **Never invent a capability.** If collateral does not support a claim, refuse and record an actionable gap.
2. **Every claim carries a citation and a date.** Unsupported claims never enter customer-facing proposals.
3. **The knowledge graph is typed.** "Related" is useless; `requires`, `conflicts_with`, and `integrates_with` dictate engineering reality.
4. **AI proposes, the Engineer decides (HITL).** High-stakes architectural decisions, pricing, and conflict overrides require explicit human approval gates.
5. **Decouple domain knowledge from code.** Playbooks, prompts, sizing heuristics, and skill definitions live in human-editable Markdown and YAML files.
6. **Tool access is standardized via MCP.** Connect external tools (filesystem, web, issue trackers) via standard JSON-RPC protocol.
7. **Customer data is confidential by default.** Multi-tenancy and permissions are enforced at the database layer (PostgreSQL RLS).
8. **Ingested content is untrusted data.** Documents never dictate instructions; prompt-injection boundaries are strictly preserved.
9. **Measured, not vibes.** Automated regression suites evaluate retrieval hit rates, citation accuracy, and workflow completion.

---

## 4. Phase Map

| Phase | Name | Status | Depends on | Outcome |
|---|---|---|---|---|
| 0 | Foundation & Security Baseline | **Partial** | — | Multi-tenant skeleton, pgvector, storage, safety seams |
| 1 | Ingestion Pipeline | **Done** | 0 | Bulk upload, chunking with citation anchors, background jobs |
| 2 | Hybrid Retrieval | **Done** | 1 | Vector (pgvector) + FTS (tsvector) with Reciprocal Rank Fusion |
| 3 | Grounded Answers | **Done** | 2 | Citation engine, structured refusals, multi-turn conversation |
| 4 | Product Catalog & Typed Graph | **Done** | 1 | Own/resold catalog, capability taxonomy, cycle/conflict detection |
| **5** | **Agentic Engine, Task DAG & Tool Harness** | **Next** | 3, 4 | Hierarchical task runner, state machine, HITL gates, MCP client |
| **6** | **Pre-Sales Playbooks & Solution Composer** | Planned | 5 | RFP response DAG, discovery-to-HLD composer, DOCX export |
| **7** | **Post-Sales Playbooks & Runbook Engine** | Planned | 5 | Install base graph, incident root-cause triage, QBR generator |
| **8** | **Workflow Workspace UI & Visual Task Tree** | Planned | 6, 7 | Execution cockpit, DAG visualizer, live step logs, HITL modals |
| **9** | **Tribal Knowledge & Dynamic Skill Authoring** | Planned | 8 | SE note linking (`[[wikilinks]]`), on-the-fly playbook creation |
| **10** | **Freshness, Vendor Sync & Hardening** | Planned | 9 | Upstream collateral scraping, staleness alerts, capacity drills |

---

## Phase 0: Foundation and security baseline (Partial)
- Tenancy data model and migration baseline in place.
- Row-Level Security (RLS) enforcement seam implemented in database models.
- Remaining: AuthN integration (OIDC/JWT), session revocation, and automated cross-tenant isolation tests.

## Phase 1: Ingestion Pipeline (Done)
- Multi-format ingestion (PDF, DOCX, PPTX, XLSX, TXT, HTML) with SSRF-safe URL fetcher.
- Deterministic chunking preserving citation anchors (page, slide, section).
- Background queue with retry, backoff, and error taxonomy.

## Phase 2: Hybrid Retrieval (Done)
- Dense vector search (pgvector HNSW cosine) combined with sparse BM25/FTS (tsvector GIN) via RRF.
- Predicate filters (product, vendor, sensitivity, approval state, date).
- Exposed diagnostic endpoint (`POST /search`) with ranking inspectability.

## Phase 3: Grounded Answers (Done)
- Grounded generation service enforcing strict citation extraction and missing-context refusal.
- Streaming SSE and synchronous generation endpoints (`POST /ask`).
- Conversation thread persistence with per-turn source inspectability.

## Phase 4: Product Catalog & Typed Graph (Done)
- Data models for Products (own/resold, vendor governance), Capabilities, ProductEdges, Reference Architectures.
- Graph traversal algorithms: DFS cycle detection on `requires`, multi-hop contradiction detection.
- Impact query engine (`query_product_impact`), coverage auditor, and AI edge suggestion curation workflow.

---

## Phase 5: Agentic Workflow Engine, Task DAG & Tool Harness

The foundational bridge that transforms the passive application into an active execution engine.

**Scope**
- **Hierarchical Task Graph (DAG) Engine (`backend/app/engine/`)**:
  - `schema.py`: Pydantic models for `WorkflowDefinition`, `TaskDefinition`, `SubTaskDefinition`, `TaskState`, and `WorkflowRunState`.
  - `loader.py`: Discovers and parses declarative `workflow.yaml` files alongside associated Markdown prompt templates (`prompts/*.md`) and rule playbooks (`rules.md`).
  - `runner.py`: Asynchronous DAG executor that tracks dependencies, spawns parallel tasks where independent, injects context memory, and manages state transitions.
- **Stateful Human-in-the-Loop (HITL) Gates**:
  - Tasks can declare `gate: human_approval` with conditional triggers (e.g. confidence < 0.85, graph conflict detected, or final deliverable sign-off).
  - Engine pauses execution, snapshots context to PostgreSQL, emits notification, and resumes on user input/override.
- **Internal Knowledge Tool Harness (`backend/app/tools/`)**:
  - Wrap Phase 1–4 capabilities into standardized callable tools:
    - `catalog_impact_query(product_id, direction)`
    - `detect_contradictions(product_ids)`
    - `check_prerequisites(product_ids)`
    - `hybrid_evidence_search(query, filters, top_k)`
- **Model Context Protocol (MCP) Client (`backend/app/mcp/`)**:
  - JSON-RPC client connecting the agent harness to standard external MCP servers:
    1. **Local Filesystem MCP**: Ingest customer RFP spreadsheets, Word templates, and SOW drafts directly from configured project folders.
    2. **Web / Fetch MCP**: Retrieve live upstream vendor release notes, datasheets, and security advisories.
    3. **Document Exporters**: Automated generation of formatted deliverables (DOCX, Markdown, JSON).
- **Persistence & API Layer**:
  - Database migration adding `workflow_runs`, `task_executions`, and `task_artifacts` tables.
  - Endpoints: `GET /workflows`, `POST /workflows/{slug}/run`, `GET /workflows/runs/{id}`, `POST /workflows/runs/{id}/resume`, and SSE real-time event stream (`/events`).

**Testing**
- Unit tests verifying DAG cycle detection, invalid dependency handling, and schema validation.
- Mock execution tests verifying topological task sequencing, input/output data flow, and error recovery.
- State persistence tests: verify paused HITL runs survive server restarts and resume accurately.
- MCP client communication tests (stdio/SSE transport).

**Exit:** an end-to-end multi-task DAG executes, invokes internal tools and an external MCP tool, halts cleanly at a human approval gate, and resumes upon user confirmation.

---

## Phase 6: Pre-Sales Playbooks & Solution Composer

Delivers the core pre-sales productivity capabilities via declarative playbooks.

**Scope**
- **RFP & Security Questionnaire Answering Playbook (`playbooks/pre-sales/rfp-response/`)**:
  - Ingestion task: parse multi-question spreadsheets/documents.
  - Analysis task: map requirements to capabilities and identify relevant products.
  - Evidence task: retrieve approved chunk citations for each requirement.
  - Verification task: audit against product graph (check for conflicts or unmet prerequisites).
  - HITL Gate: architect reviews low-confidence items and approves answers.
  - Export task: render completed questionnaire in original template format via Exporter tool.
- **Solution Composer Playbook (`playbooks/pre-sales/solution-composer/`)**:
  - Discovery task: extract pain points, constraints (budget, timeline, deployment type), and incumbent vendors from meeting notes.
  - Candidate bundle generation: scored on coverage, zero `conflicts_with` edges, and prerequisite satisfaction.
  - Gap Analysis: explicitly list requirements that cannot be satisfied with citations explaining why.
  - Deliverable generation: draft High-Level Design (HLD) document, bill of materials (BOM), and Statement of Work (SOW).
- **Competitive Battlecard & Objection Handling Playbook**:
  - Fast comparative lookup pulling verified counter-claims strictly from approved collateral.

**Testing**
- Golden scenario regression set: 20+ past RFPs and deal requirements with known-good solutions.
- Negative tests: unsatisfiable requirements strictly produce gaps, never hallucinated products or fake capabilities.
- Conflict tests: a known-incompatible pair is never proposed in an HLD bundle.

**Exit:** an 80-question RFP is ingested and processed through the workflow, producing cited answers, flagging gaps, pausing for HITL review, and exporting a clean deliverable.

---

## Phase 7: Post-Sales Playbooks & Runbook Engine

Extends the execution engine to post-sales implementation, operations, and account growth.

**Scope**
- **Account Install Base Graph**:
  - Model deployed customer configurations as graph instances linked to catalog products and version nodes.
- **Incident Triage & Root Cause Playbook (`playbooks/post-sales/incident-triage/`)**:
  - Ingest customer error logs or escalation tickets.
  - Correlate installed components against known issues, vendor errata, and prerequisite graphs.
  - Generate ranked diagnostic hypotheses and step-by-step remediation runbooks with citations.
- **Upgrade Impact Audit Playbook**:
  - Given a target version upgrade for Product X, traverse the graph to compute all downstream systems affected, required prerequisite upgrades, and breaking changes.
- **QBR Pack & Expansion Signal Generator**:
  - Analyze customer adoption, resolved escalations, and install base.
  - Identify adjacent portfolio products that satisfy unmet capabilities or replace EOL components.

**Testing**
- Labeled evaluation against past resolved escalation cases.
- EOL propagation tests: marking a product or version EOL flags all affected customer install bases.

**Exit:** an engineer inputs an escalation scenario and the system generates a validated diagnostic runbook matching historical resolution.

---

## Phase 8: Workflow Workspace UI & Visual Task Tree

Upgrades the frontend from a chat box to a high-performance **Solutions Engineering Cockpit**.

**Scope**
- **Workflow Gallery**: Browse and launch available pre-sales, post-sales, and architecture playbooks.
- **Visual Task Tree / DAG Inspector**:
  - Interactive graph showing task nodes, dependencies, and real-time execution states (Pending, Running, Waiting for Approval, Completed, Failed).
  - Live execution drawer: inspect tool calls, LLM prompts, input/output data, and log streams.
- **Human-in-the-Loop (HITL) Decision Modal**:
  - Clean interface for reviewing flagged architectural contradictions, approving capability mappings, or editing drafted RFP answers before resumption.
- **Deliverable & Artifact Viewer**:
  - Dedicated previewer for generated HLDs, SOWs, RFP tables, and runbooks with inline citation popovers and direct download buttons (DOCX, Markdown).

**Testing**
- Component tests for DAG rendering, state transition animations, and HITL form submissions.
- End-to-end browser walkthrough testing of workflow initiation, live streaming, and export downloads.

**Exit:** user can launch an RFP or Solution Composer workflow, watch real-time task progression, resolve a pause gate, and inspect the final artifact without touching the terminal.

---

## Phase 9: Notes, Tribal Knowledge & Dynamic Skill Authoring

Brings engineer-authored knowledge into the active execution loop.

**Scope**
- Markdown editor with live preview, frontmatter metadata, and `[[wikilinks]]` linking notes directly to products, capabilities, and accounts.
- **Tribal Knowledge Capture**: Prompts the SE after completing a deal or troubleshooting incident to write up undocumented integration quirks or workarounds.
- **Dynamic Skill & Playbook Authoring**:
  - UI wizard and template for creating new playbooks and skills by dropping Markdown files into `playbooks/` and `skills/`.
  - Hot-reloading of playbooks without requiring backend restarts.

**Testing**
- Link integrity tests across entity renames and deletions.
- Re-indexing validation: freshly saved SE notes are immediately discoverable by retrieval tools.

**Exit:** an SE authors an integration note, and a subsequent RFP workflow immediately cites that note in its answer.

---

## Phase 10: Freshness, Vendor Sync & Hardening

Guarantees data integrity over time and hardens the platform for production.

**Scope**
- **Vendor Collateral Monitoring for Resold Products**:
  - Web fetcher monitors upstream vendor documentation URLs and flags changed datasheets or expired collateral.
- **Coverage & Staleness Dashboard**:
  - Flags products with stale review dates, unmapped capabilities, or thin collateral.
- **Enterprise Hardening**:
  - SAML/OIDC SSO, session policies, backup and tested restore drills.
  - Load testing at 10x projected corpus and concurrency limits.

**Testing**
- Automated upstream scraper detection tests on sample vendor sites.
- Disaster recovery: end-to-end database and object store backup and restoration verification.

**Exit:** weekly staleness report runs unattended, and restore drills pass under SLA.

---

## 5. Testing Strategy Across All Phases

| Layer | Covers | Runs |
|---|---|---|
| **Unit** | Chunking, parsing, graph algorithms, DAG cycle detection | Every commit |
| **Tool Registry** | Input/output schema validation, tool execution safety | Every PR |
| **Playbook Syntax** | YAML schema, missing prompt files, valid dependencies | Every PR |
| **State Machine** | Task progression, HITL pause/resume, error handling | Every PR |
| **Integration** | API routes, PostgreSQL transactions, RLS filters | Every PR |
| **Retrieval Evaluation** | Labeled question set, hit-rate, precision | Nightly & pre-release |
| **Generation Evaluation** | Citation validity, refusal on unsupported questions | On prompt/model changes |
| **Golden Scenarios** | 20+ real RFP and deal scenarios scored against known-good solutions | Before release |
| **Adversarial Security** | Prompt injection via untrusted RFPs, SSRF, tool breakout | Nightly |

---

## 6. Security Posture

| Risk | Control | Phase |
|---|---|---|
| **Prompt Injection via Customer RFPs** | Ingested text strictly delimited as untrusted data; system prompts forbid instruction override | 1, 5 |
| **Unauthorized Tool Execution** | Strict allowlist of tool schemas; no arbitrary shell execution or `eval()` | 3, 5 |
| **Local Filesystem MCP Traversal** | Path containment: access restricted to explicitly mounted workspace directories | 5 |
| **SSRF via Upstream Web Fetcher** | Deny private IP ranges, cloud metadata services, and internal redirects | 1, 5 |
| **Data Leakage Across Customers** | PostgreSQL Row-Level Security (RLS) + organization scoping on every query | 0 |
| **Disclosing Vendor-Restricted Data** | `vendor_restricted` metadata label; export blocks restricted data unless override is approved and audited | 4, 6 |
| **Untracked High-Stakes Actions** | Append-only audit log for all HITL approvals, overrides, and document exports | 0, 5 |

---

## 7. Scalability Posture

- **Compact Footprint**: 20 products, 50 documents, and 50 users means computational efficiency is trivial if data structures are clean.
- **Asynchronous Execution**: Workflow DAG execution runs via standard async Python; long-running LLM and tool steps run non-blocking.
- **State in PostgreSQL**: Workflow execution states, step outputs, and artifacts are stored in relational tables (`workflow_runs`, `task_executions`), eliminating the need for complex external message brokers.
- **Client Streaming**: Real-time step progress and LLM generation streamed to the browser via Server-Sent Events (SSE).

---

## 8. Sequencing & Immediate Next Steps

1. **Immediate Focus (Phase 5)**:
   - Build the DAG Engine core (`backend/app/engine/schema.py`, `loader.py`, `runner.py`).
   - Wrap existing Phase 1–4 capabilities into `backend/app/tools/` (catalog impact query, contradiction detector, hybrid search).
   - Integrate MCP client for Local Filesystem, Web Fetcher, and DOCX/Markdown exporters.
   - Implement the `human_approval` pause/resume mechanism and API endpoints.
2. **Subsequent Step (Phase 6)**:
   - Author the declarative `rfp-response` and `solution-composer` playbooks under `playbooks/pre-sales/`.
3. **Frontend Integration (Phase 8)**:
   - Build the Workflow Workspace UI and Visual Task Tree inspector.