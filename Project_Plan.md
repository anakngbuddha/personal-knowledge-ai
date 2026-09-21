# Project Plan: Solution Engineering Knowledge Workspace (Enterprise Multi-Tenant)

Status: **Rev 4 (2026-09-20)**. Supersedes Rev 3, Rev 2, and `docs/ROADMAP.md`.

Rev 4 grounds the architecture directly in the codebase following a comprehensive architectural and code audit. It commits decisively to the **Multi-Tenant Enterprise** path, promotes Phase 0 to an immediate blocking prerequisite, replaces the ungrounded async DAG design with our proven PostgreSQL `SELECT FOR UPDATE SKIP LOCKED` queue substrate from `app/jobs/queue.py`, splits the monolithic Phase 5 into three verifiable milestones (5a, 5b, 5c), defers premature MCP in favor of direct Python tools, and elevates the Golden RFP evaluation set into a dedicated gate (Phase 6.5).

---

## 0. Decided Parameters

| Question | Decision | Consequence |
|---|---|---|
| **Platform Identity** | **Multi-tenant Enterprise SE Platform** | Real PostgreSQL RLS policies (`CREATE POLICY`), cryptographic JWT/OIDC authentication, per-org isolation, and audit logging are non-negotiable. |
| **Authentication & AuthZ** | **Cryptographic JWT / OIDC + RBAC** | Eradicate unverified dev headers (`X-Org-Id`, `X-User-Id`, `X-User-Role`). Enforce signed token validation, role hierarchy (`admin`, `solutions_engineer`, `sales`, `viewer`), and account scoping. |
| **Catalog Scope** | **Own products and resold third-party products** | Provenance modeled on every entity (`vendor`, `source_of_truth`, `partner_tier`, `support_owner`, `contract_constraints`). |
| **Collateral Ownership** | **Single owner (initially)** | Lightweight governance: review dates and an audit dashboard, avoiding bloated approval bureaucracy while tracking partner document staleness. |
| **CRM Integration** | **Out of scope** | Accounts and opportunities are native relational records with CSV import/export only. |
| **Scale, Year One** | **~20 products, ~50 documents, ~50 users** | Dense, high-accuracy bar. One PostgreSQL instance with pgvector. Focus on graph accuracy and workflow precision rather than distributed cluster engineering. |
| **Task Execution Engine** | **Durable PostgreSQL Queue Substrate** | Generalize `app/jobs/queue.py` into a dependency-aware `task_executions` table using `SELECT FOR UPDATE SKIP LOCKED`. No in-process async DAG runner; crash and restart survival come free. |
| **Human-in-the-Loop (HITL)** | **Database Status (`waiting_approval`)** | Pausing at approval gates is a row state, not an in-memory process. Resume is an `UPDATE` endpoint. Runs survive server restarts and multi-day pauses by construction. |
| **Tool Calling Standard** | **Native Python tools (Phases 5–8) + MCP client (Phase 9)** | Catalog/retrieval stay in-process Python functions. Phase 9 adds a sandboxed MCP client for Playwright, Microsoft 365 Graph, and Brave Search. |

---

## 1. What This Is

A high-assurance **Agentic Operating System and Knowledge Workspace** for enterprise Pre-Sales Engineers, Post-Sales Consultants, and Solution Architects. It grounds multi-step workflows (RFP answering, solution composition, incident root-cause triage) in an evidence-backed, typed knowledge graph with strict multi-tenant isolation.

```text
┌─────────────────────────────────────────────────────────────────────────┐
│                        PLAYBOOK & WORKFLOW LAYER                        │
│  Playbooks & Rules (Markdown/YAML)  │  Deliverable Exporters (Native)   │
│  - RFP Responder Workflow           │  - python-docx (Formatted tables) │
│  - Solution Composer (HLD/BOM)      │  - Markdown / JSON Deliverables   │
├─────────────────────────────────────────────────────────────────────────┤
│                  DURABLE QUEUE-BASED TASK RUNNER                        │
│  task_executions (SELECT FOR UPDATE SKIP LOCKED with dependency check)  │
│  [Task 1: Ingest] ──> [Task 2: Evaluate] ──> [Task 3: Graph Audit]     │
│       │                                             │                   │
│       ▼                                             ▼                   │
│  [status = 'waiting_approval'] (HITL Gate) ──> [Task 4: Export DOCX]    │
├─────────────────────────────────────────────────────────────────────────┤
│                   KNOWLEDGE & TOOL SUBSTRATE (Phases 1 - 4)             │
│  Hybrid Search (pgvector + FTS)  │ Typed Product Graph │ Citation Engine│
├─────────────────────────────────────────────────────────────────────────┤
│                     SECURITY & ISOLATION BASELINE                       │
│    PostgreSQL Row-Level Security (RLS)  │ Cryptographic JWT Validation  │
└─────────────────────────────────────────────────────────────────────────┘
```

---

## 2. Core Principles

1. **Security is structural, not an afterthought.** Real PostgreSQL RLS policies enforce tenant boundaries at the database layer; application-level `.where()` clauses are never trusted as the sole isolation mechanism.
2. **Never invent a capability.** If collateral does not support a claim, refuse and record an actionable gap.
3. **Every claim carries a citation and a date.** Unsupported claims never enter customer-facing proposals.
4. **The knowledge graph is typed.** "Related" is useless; `requires`, `conflicts_with`, and `integrates_with` dictate engineering reality.
5. **AI proposes, the Engineer decides (HITL).** High-stakes architectural decisions, pricing, and conflict overrides pause statefully for human sign-off.
6. **Measured, not vibes.** Labeled evaluation sets and written baselines must exist before declaring retrieval or generation "Done."
7. **Reuse battle-tested primitives.** Rely on PostgreSQL transactional queues (`SKIP LOCKED`) instead of inventing fragile in-process async execution engines.
8. **Ingested content is untrusted data.** Documents never dictate instructions; prompt-injection boundaries are strictly preserved.

---

## 3. Restructured Phase Map

| Phase | Name | Status | Depends on | Outcome |
|---|---|---|---|---|
| **0** | **Security Foundation & PostgreSQL RLS** | **Done** | — | Cryptographic JWT auth, real PostgreSQL RLS policies, audit log, CI isolation tests |
| **1** | **Ingestion Pipeline** | **Done** | 0 | Multi-format upload, deterministic chunking, citation anchors, background queue |
| **2** | **Hybrid Retrieval** | **Done\*** | 1 | Vector (pgvector) + FTS (tsvector) with RRF fusion and metadata filters |
| **3** | **Grounded Answers** | **Done\*** | 2 | Grounded generation, citation extraction, refusal on missing context |
| **4** | **Product Catalog & Typed Graph** | **Done** | 1 | Own/resold catalog, capability taxonomy, cycle/conflict detection, impact queries |
| **4.5**| **Eval Substrate & Written Baseline** | **Next** | 2, 3 | Repay Phase 2/3 debt: 50-question labeled set, retrieval baseline, generation baseline |
| **5a** | **Single-Turn Tool Calling in LLM** | Planned | 3, 4 | Extend `LLMProvider` with tool schemas and execution loop; wrap catalog & retrieval tools |
| **5b** | **Durable Queue-Based Task Runner** | Planned | 5a | Generalize `app/jobs/queue.py` into `task_executions` with dependency-aware `claim()` |
| **5c** | **Human-in-the-Loop (HITL) as a Status** | Planned | 5b | `waiting_approval` status, resume `UPDATE` endpoint, and audit trail |
| **6** | **RFP Responder Playbook (End-to-End)** | Planned | 5c | Ingest spreadsheet $\rightarrow$ extract requirements $\rightarrow$ tool-grounded answers $\rightarrow$ HITL $\rightarrow$ DOCX export |
| **6.5**| **Golden Scenario Evaluation Set** | Planned | 6 | 20 real past RFPs scored against known-good solutions (the ultimate trust gate) |
| **7** | **Workflow Workspace UI & Task Tree** | Planned | 6 | Execution cockpit, task progress visualizer, step logs, HITL decision modal |
| **8** | **Solution Composer & Post-Sales Playbooks** | Planned | 6.5, 7 | Discovery-to-HLD composer, BOM generator, incident triage runbook |
| **9** | **Model Context Protocol (MCP) Integration** | **Done** | 8 | First-party MCP client for Playwright, Microsoft 365 Graph, and Brave Search (not Jira/ServiceNow/GitHub) |
| **10**| **Notes, Freshness & Enterprise Hardening** | **Done** | 8 | SE tribal notes (`[[wikilinks]]`), upstream vendor doc monitoring, capacity drills |

*\*Note: Phases 2 and 3 code is fully implemented, but formal sign-off requires the empirical baseline in Phase 4.5.*

---

## Phase 0: Security Foundation & PostgreSQL RLS (IMMEDIATE PRIORITY)

The non-negotiable security baseline for a multi-tenant platform.

**Scope**
- **Authentication & Authorization**:
  - Replace header-spoofing `resolve_principal` with cryptographic JWT validation (Auth0 / OIDC or signed bearer tokens).
  - RBAC matrix: `admin`, `solutions_engineer`, `sales`, `viewer`, plus explicit account-level data grants.
  - **Role Enum Reconciliation**: Reconcile the RBAC role set with current code (`app/security/labels.py` and `app/security/principal.py`, which use `Role.OWNER`, `Role.ADMIN`, `Role.SOLUTIONS_ENGINEER`, `Role.SALES`, `Role.VIEWER`). Explicitly audit and migrate enum values, test fixtures across `backend/tests/test_permissions.py`, `Principal.is_owner()`, and all `normalize()` call sites.
- **Real PostgreSQL Row-Level Security (RLS)**:
  - Add `ALTER TABLE ... ENABLE ROW LEVEL SECURITY` and `FORCE ROW LEVEL SECURITY` across all tenant-scoped tables (`documents`, `chunks`, `products`, `product_edges`, `reference_architectures`, `conversations`, `jobs`).
  - **Session RLS Injection Hook (`backend/app/db/session.py` & `backend/app/security/deps.py`)**: Implement a request-scoped session dependency (e.g., `get_tenant_db(principal: Principal = Depends(get_current_principal))`) that executes `SET LOCAL app.current_org_id = :org_id` on the session connection on every single request. This guarantees queries execute within the active tenant's transaction boundary and prevents RLS from silently failing closed (returning empty sets).
  - Database policies: `CREATE POLICY tenant_isolation_policy ON <table> USING (org_id = current_setting('app.current_org_id')::uuid)`.
- **Append-Only Audit Log**:
  - `audit_logs` table tracking user ID, org ID, action (`view`, `export`, `approve`, `override`), resource type, and timestamp.
- **CI & Automated Isolation Tests**:
  - Add GitHub Actions workflow (`.github/workflows/test.yml`).
  - Permanent cross-tenant isolation test suite: every endpoint verifies that a principal from Org A receives 404 (never 403 or data leaks) when querying Org B resources.

**Exit:** header-based spoofing is impossible, real PostgreSQL RLS is active on all tables, and CI executes cross-tenant isolation tests on every commit.

---

## Phase 4.5: Evaluation Substrate & Written Baseline

Closing the measurement gap from Phases 2 and 3 before building agentic workflows on top of them.

**Scope**
- Populate `docs/eval/questions.json` with 50+ real, hand-crafted solutions engineering questions categorized by shape (direct lookup, multi-product compatibility, negative/unsupported, competitive claims, sizing).
- Run `scripts/seed_eval_set.py` to index the golden benchmark set.
- Run `scripts/run_eval.py --out docs/retrieval-baseline.md` to establish written precision, recall, and hit-rate baselines for vector-only, keyword-only, and hybrid search.
- Run `scripts/run_generation_eval.py --out docs/generation-baseline.md` to benchmark citation accuracy and refusal correctness.

**Exit:** written retrieval and generation baselines committed to the repository, proving that retrieval accuracy meets the standard required for automated proposals.

---

## Phase 5a: Single-Turn Tool Calling in LLM

Extending the LLM provider to support tool use before attempting complex task graphs.

**Scope**
- **LLMProvider Refactoring (`app/llm/base.py`)**:
  - Add `tools: list[ToolDefinition] | None = None` parameter to generation methods.
  - Implement tool-call request/response schema parsing for Gemini/OpenAI providers.
  - Implement a bounded single-turn tool execution loop: LLM calls tool $\rightarrow$ backend executes function $\rightarrow$ LLM synthesizes cited response.
- **Internal Tool Registry (`app/tools/`)**:
  - `tool_catalog_impact`: wraps `app/catalog/graph.py::query_product_impact`.
  - `tool_detect_contradictions`: wraps `app/catalog/graph.py::detect_contradictions`.
  - `tool_check_prerequisites`: wraps `app/catalog/graph.py::detect_cycles_in_requires`.
  - `tool_hybrid_search`: wraps `app/retrieval/hybrid.py`.
- Expose tool-enabled generation to `POST /ask` via an optional `enable_tools: bool` flag.

**Exit:** `/ask` can answer "What are the prerequisite conflicts if I deploy Product X?" by autonomously querying graph tools and citing the results.

---

## Phase 5b: Durable Queue-Based Task Runner

Building the workflow engine on top of our existing, battle-tested queue machinery.

**Scope**
- **Data Model (`task_executions` table)**:
  - Columns: `id`, `workflow_run_id`, `task_slug`, `depends_on_slugs` (array), `status` (`pending`, `running`, `waiting_approval`, `succeeded`, `failed`), `input_payload` (JSONB), `output_payload` (JSONB), `leased_until`, `worker_id`, `retry_count`.
- **Upfront Task Materialization**:
  - The workflow loader materializes every task row for a run upfront at start time (`status = 'pending'`), before any claiming begins. This guarantees that the `NOT EXISTS` check accurately evaluates incomplete upstream dependencies rather than prematurely claiming downstream tasks whose prerequisites have not yet been inserted.
- **Dependency-Aware Claim Mechanism**:
  - Adapt `app/jobs/queue.py::claim()` to enforce:
    ```sql
    SELECT * FROM task_executions
    WHERE status = 'pending'
      AND (
        depends_on_slugs IS NULL OR
        NOT EXISTS (
          SELECT 1 FROM task_executions dep
          WHERE dep.workflow_run_id = task_executions.workflow_run_id
            AND dep.task_slug = ANY(task_executions.depends_on_slugs)
            AND dep.status != 'succeeded'
        )
      )
    ORDER BY created_at ASC
    FOR UPDATE SKIP LOCKED
    LIMIT 1;
    ```
- **Sequential Execution Pool**:
  - Worker runs within existing synchronous database session limits without starving the pool (`pool_size=5, max_overflow=5`).
- Crash and restart survival guaranteed by database transactions.

**Exit:** a 3-task linear DAG executes sequentially, passes data between steps, survives an intentional process crash mid-run, and finishes successfully upon restart.

---

## Phase 5c: Human-in-the-Loop (HITL) as a Status

Implementing human review gates as simple database states rather than complex memory suspensions.

**Scope**
- **Approval Gate**:
  - Tasks marked with `gate: human_approval` set `status = 'waiting_approval'` upon completing their draft output.
  - Because `status != 'pending'`, the queue never claims downstream dependent tasks.
- **Resume Endpoint**:
  - `POST /workflows/runs/{run_id}/tasks/{task_slug}/approve`:
    - Updates task status from `waiting_approval` $\rightarrow$ `succeeded` (with optional payload edits).
    - Records the user's approval in `audit_logs`.
    - Automatically unlocks downstream tasks for claiming.
  - `POST /workflows/runs/{run_id}/tasks/{task_slug}/reject`: sets status to `failed` and halts the workflow run.

**Exit:** a workflow halts at an approval gate, remains paused overnight, and resumes execution cleanly upon an API approval call.

---

## Phase 6: RFP Responder Playbook (End-to-End)

Proving the complete loop on one high-value pre-sales deliverable before building multiple playbooks.

**Scope**
- **Playbook Definition (`playbooks/pre-sales/rfp-response/workflow.yaml`)**:
  - Step 1 (`parse_rfp`): Extract questions from uploaded CSV/XLSX.
  - Step 2 (`evaluate_capabilities`): Match questions to catalog capabilities and product graph.
  - Step 3 (`retrieve_evidence`): Retrieve cited chunks from approved collateral.
  - Step 4 (`draft_responses`): Generate cited answers with compliance status (Compliant / Partially / Non-Compliant).
  - Step 5 (`human_gate`): Pause for SE review on any answer with confidence < 0.85 or unmet prerequisites.
  - Step 6 (`export_deliverable`): Render completed questionnaire into a formatted Word document (`.docx`) with styled tables and citation appendices using `python-docx`.
- Dedicated multi-tenant upload and execution endpoint: `POST /workflows/rfp/run`.

**Exit:** an SE uploads a real customer RFP spreadsheet, reviews drafted answers in the approval queue, and downloads a formatted `.docx` deliverable containing zero unapproved or uncited claims.

---

## Phase 6.5: Golden Scenario Evaluation Set

The true trust gate for the solution engineering engine.

**Scope**
- Curate a golden benchmark suite of **20 real past RFPs and technical solution scenarios** with known-good answers.
- Automated regression runner: runs the RFP responder across all 20 scenarios.
- Scored metrics:
  - Requirement coverage rate ($\ge 90\%$).
  - Zero hallucinated capabilities or ungrounded claims.
  - Zero bundles containing conflicting products (`conflicts_with`).
  - 100% adherence to customer constraints (e.g., on-prem only, vendor restrictions).

**Exit:** regression test suite runs unattended against all 20 scenarios, producing a verified pass rate committed to `docs/eval/golden-scenarios-report.md`.

---

## Phase 7: Workflow Workspace UI & Task Tree

Providing a dedicated cockpit for solutions engineers in React.

**Scope**
- **Playbook Gallery**: Browse available workflows (RFP Responder, Solution Composer).
- **Visual Task Tree**: Live status visualizer showing nodes (`pending`, `running`, `waiting_approval`, `succeeded`, `failed`).
- **HITL Review Modal**:
  - Side-by-side view of extracted requirement, drafted response, retrieved citations, and graph conflict warnings.
  - Inline editing and "Approve & Resume" action.
- **Deliverable Downloader**: Direct download button for generated DOCX and Markdown deliverables.

**Exit:** an engineer can upload an RFP, monitor execution progress, approve review gates, and download the finished proposal entirely within the browser.

---

## Phase 8: Solution Composer & Post-Sales Playbooks

Extending the proven engine to High-Level Design (HLD) generation and post-sales runbooks.

**Scope**
- **Solution Composer Playbook**:
  - Ingest customer discovery notes $\rightarrow$ extract constraints $\rightarrow$ compose candidate bundles $\rightarrow$ validate against `ProductEdge` graph $\rightarrow$ generate Bill of Materials (BOM) and HLD draft.
- **Incident Root-Cause Triage Playbook**:
  - Ingest customer error logs $\rightarrow$ query customer install base $\rightarrow$ traverse dependency graph $\rightarrow$ output step-by-step troubleshooting runbook with citations.
- **Upgrade Impact Audit Playbook**:
  - Compute transitive downstream impacts and breaking changes for proposed product upgrades.

**Exit:** Solution Composer successfully generates an HLD and BOM matching past manual solutions on the golden scenario set.

---

## Phase 9: Model Context Protocol (MCP) Integration

First-party MCP client for SE-relevant external tools, wired into the Phase 5a Python tool loop.

**Scope**
- JSON-RPC MCP client (official Python SDK) with stdio (`npx`) and Streamable HTTP transports.
- Starting servers (not Jira / ServiceNow / GitHub):
  1. Playwright (`@playwright/mcp`) — public documentation sites, vendor portals, web forms (headless, SSRF-gated).
  2. Microsoft 365 / Graph (`@softeria/ms-365-mcp-server`, read-only) — Outlook, OneDrive/SharePoint, Excel, calendar, contacts.
  3. Brave Search (`@brave/brave-search-mcp-server`) — live web and news search.
- Tool sandbox: name allowlists, result size caps, `wrap_untrusted`, Playwright URL checks via `app/net/ssrf.py`.
- Tenant-scoped `mcp_integrations` rows with Fernet-encrypted secrets and PostgreSQL RLS.
- Admin Integrations API/UI; Grounded Chat `enable_tools` toggle.

**Exit:** `/ask` with tools can Brave-search, Playwright-snapshot a public docs page, and Graph-search files. Unit tests use a Fake MCP client and never spawn browsers.

---

## Phase 10: Notes, Freshness & Enterprise Hardening

Finalizing institutional knowledge capture and operational resilience.

**Scope**
- Markdown authoring with `[[wikilinks]]` linking SE tribal notes directly to products and accounts.
- Scheduled vendor collateral scraper monitoring upstream URLs for datasheet modifications.
- SAML / OIDC SSO integration and automated database restore drills.

**Exit:** disaster recovery restore drill executed successfully within SLA; upstream doc modification triggers a staleness alert.

---

## 4. Documentation Hygiene & Repo Synchronization

To eliminate documentation rot and maintain a single source of truth:
1. **Single Plan of Record**: `Project_Plan.md` (Rev 4) is the sole authoritative plan.
2. **`STATUS.md` Synchronization**: Update `STATUS.md` to accurately reflect Phase 0 as Immediate, Phases 1–4 as Done, and Phase 4.5 as Next.
3. **Deprecate Dead Docs**: Archive `docs/ROADMAP.md` and eliminate duplicate agent configuration files.
4. **Git Hygiene**: Add `graphify-out/` to `.gitignore` and purge `__pycache__` from git tracking.