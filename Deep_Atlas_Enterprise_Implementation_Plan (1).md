# Deep Atlas Enterprise Sales and Quotation Platform

## Revised implementation plan — 30 September 2026

## Confirmed scope update — resumed implementation

The user confirmed the following decisions on 30 September 2026. These override the earlier ERP/CRM, tax, discount, and contract-cost requirements elsewhere in this document:

- Deep Atlas stores accounts, opportunities, observations, policies, approvals, and issued quote versions internally. No external ERP or CRM connector is required. Internal authenticated writeback remains authorized; quote issuance and version changes remain audited.
- New quotations use **raw public product list prices**, multiplied by explicit quantities and usage. Tax, discounts, markup, and commercial margin adjustments are zero. New drafts reject non-public observations and legacy policies carrying tax or discount/margin settings. Existing immutable historical versions remain preserved.
- Focus pilot mappings on Southeast Asia. Huawei includes AP-Manila (`ap-southeast-5`) and AP-Singapore (`ap-southeast-3`). Exact region and SKU mappings remain reviewed; the system does not silently substitute another region. Region codes were checked against [Huawei's official region table](https://support.huaweicloud.com/intl/en-us/usermanual-organizations/org_03_0082.html).
- Verification permits only necessary environment-dependent skips and at most seven corrective retries. Live vendor credentials and PostgreSQL with pgvector are still required for their corresponding production checks.

Implementation and verification evidence for this continuation is maintained in [docs/DEEP_ATLAS_IMPLEMENTATION_STATUS.md](docs/DEEP_ATLAS_IMPLEMENTATION_STATUS.md). Passing the local verifier is not evidence that every phase's production exit gate has passed.

## Final goal

An authorized sales team can turn a customer's requirements into a reviewed solution and a reproducible quotation. Deep Atlas should identify gaps, recommend compatible products, obtain evidence and current price inputs, calculate commercial terms deterministically, route exceptions for approval, and export a customer-safe proposal. Every decision must be traceable to a tenant, opportunity, source, price snapshot, rule version, and approver. Multiple organizations must be able to use the same deployment without seeing or influencing one another's data, tools, costs, or workflows.

The first production slice is **opportunity → requirements → solution bill of materials → priced draft → approval → immutable quote version → proposal**. The committed platform scope also includes Huawei Cloud, AWS, Azure, and Google Cloud pricing APIs; Firecrawl and Exa MCP research; and Google Sheets integration. These follow the first complete quote path in measured phases, with all four CSPs and the three requested integrations included in the target system.

## 1. Codebase assessment

This plan is based on the repository as it exists today. “Present” means code exists; it does not imply production readiness or deployment configuration.

| Capability | Existing implementation | Work still needed |
|---|---|---|
| Tenant identity | `Organization`, `Workspace`, membership, `Principal`, token validation, SSO modules, and tenant scoping in `backend/app/security/` and `backend/app/db/` | Require and verify RLS in production; remove reliance on owner development mode; add explicit opportunity and account permissions. |
| Knowledge and evidence | Documents, chunks, pgvector HNSW migration, hybrid retrieval, citations, source sensitivity and approvals | Bind evidence to requirement and quote versions; apply retention and export rules; keep crawled commercial claims pending review. |
| Product model | `Product`, capabilities, approved `ProductEdge`, selling contexts, reference architectures, catalog review | Add provider SKU/region mappings, price eligibility, lifecycle and version semantics. |
| Sales assistance | Customer brief extraction and evidence-backed recommendations in `backend/app/advisor/`; RFP playbook | Promote editable briefs into structured opportunity requirements and coverage decisions. |
| Execution | Bounded tool loop, durable workflow task queue with leases, approval state, action review | Use the existing workflow engine for deal steps and exception approvals; add idempotency and tenant-aware fairness. |
| Integrations | Tenant-scoped MCP integration store and allowlist; Brave, Playwright, MS365; web fallback/crawler | Add Firecrawl and Exa as explicit tenant-managed MCP integrations and Google Sheets through the Sheets API with a controlled MCP tool surface. |
| Quote/pricing | No native pricing adapter, commercial policy engine, quote entity, or immutable price snapshot found | Implement these as the central new capability. |

**Important distinction:** `graphify-out/graph.json` is the repository's code-navigation graph. Runtime product and solution relationships live in the PostgreSQL catalog tables. Do not use Graphify as a customer-data store or merge all tenants into one visible business graph.

## 2. Corrections to the previous plan

1. **Put tenant governance before connector breadth.** The earlier order began with catalog and four CSP adapters while commercial permissions, quote ownership, and approval policy were underspecified. Establish these before any customer-facing quotation.
2. **Use one vertical sales workflow before four-provider parity.** A credible quote for one provider with all required components, taxes/assumptions, snapshots, and approvals has more value than a broad SKU lookup that cannot be sold. Add providers only when normalization and coverage tests pass.
3. **Treat a price as a conditional offer, not a number.** Public rate, contract cost, sell price, discount, currency, term, unit, tier, region, effective time, and tax treatment are different fields. A public CSP API does not provide a customer's final resale price.
4. **Keep commercial records relational.** Use typed PostgreSQL entities and constraints for opportunities, requirements, price snapshots, quotes, approvals, and audit events. Project only approved, scoped relationships into the existing product graph and its UI views.
5. **Reuse the durable workflow queue.** Extend `backend/app/workflows/` and the bounded tool loop. Do not create a second general orchestrator or use FastAPI background tasks for long-running, revenue-critical operations.
6. **Use MCP at the integration boundary.** Firecrawl, Exa, and a restricted Google Sheets MCP surface are planned workstreams. Provider pricing, calculations, approval policies, and ERP/CRM writes belong in backend services; a pricing MCP wrapper can expose safe read tools after those services exist.
7. **Separate research from approved claims.** Web results may suggest leads, but a battle-card or proposal claim needs source, validity, reviewer, and scope. Research tools must not promote claims automatically.
8. **Distinguish quote from order.** Deep Atlas drafts and approves quotes; the ERP/CRM remains the system of record for orders, contracts, and billing unless the organization explicitly delegates a specific operation.

## 3. Target operating model

```text
Customer / RFP / CRM
        ↓
Tenant-scoped opportunity workspace
        ↓
Structured requirements + coverage matrix
        ↓
Approved catalog + solution dependency graph + authorized evidence
        ↓
Provider price snapshots + ERP contract terms + commercial policy
        ↓
Deterministic bill of materials and quote calculator
        ↓
Approval workflow → immutable quote version → customer-safe proposal
        ↓
CRM/ERP handoff, follow-up, and analytics
```

The LLM extracts requirements, explains tradeoffs, and drafts language. Backend code selects permitted data, evaluates rules, computes totals, and enforces state transitions. The user can edit assumptions, mappings, quantities, and wording before approval. No tool receives a model-supplied `org_id`, access token, or unrestricted customer identifier.

### Enterprise tenancy and ownership

- `Organization` is the isolation boundary. `Workspace` scopes collaboration. An `Opportunity` belongs to exactly one organization and workspace; `Customer`/`Account` belongs to an organization and may be linked to more than one workspace only by an explicit grant.
- Every new row, queue task, cache key, object key, search filter, graph query, export, and audit event carries or derives tenant scope. Public catalog rates may be shared only as non-sensitive provider data; contract prices, margins, customer records, prompts, and generated artifacts are tenant private.
- Apply PostgreSQL RLS to new tenant tables; use a non-bypass application role and set `rls_required` in production. Recheck membership and opportunity permissions at API entry and at delayed worker execution. Review existing system-session bypasses before routing commercial tasks through workers.
- Use roles for broad capabilities and resource grants for account/opportunity access. Separate `sales`, `solutions engineer`, `commercial approver`, `manager`, and `integration administrator`; require explicit approval authority and thresholds for discounts and margin exceptions. Deny by default when an assignment or policy is absent.
- Encrypt connector credentials with per-tenant scoping and rotation. Keep them out of model context and audit payloads. Log access to customer commercial data and exports.
- Enforce tenant quotas for LLM tokens, research calls, price refreshes, active jobs, storage, and exports; schedule jobs fairly so one organization cannot monopolize workers.
- Review the current `rls_required=False` and `freshness_auto_approve=True` defaults before enterprise deployment. Production must enforce RLS, and external pages used for commercial claims must await explicit review.

## 4. New sales feature: opportunity coverage workspace

An opportunity is the durable home for a sales cycle, rather than a chat transcript or free-form note. It links CRM identity, customer, owner, participants, expected close date, stage, currency, market, documents, and quote versions. The existing customer-brief extraction becomes an import path, with human review before requirements are accepted.

For each requirement, record its original passage or customer statement, normalized fields, priority, acceptance criterion, status (`unreviewed`, `covered`, `partial`, `gap`, `excluded`), chosen solution component, evidence, assumptions, reviewer, and change history. The **coverage matrix** answers “which must-haves are satisfied, which are not, and why?” A quote cannot reach approval while a mandatory requirement is unresolved unless an authorized exception records the reason and customer-facing caveat.

Useful sales additions, in priority order:

1. **RFP response matrix:** import RFP sections, identify obligations, map evidence and products, assign unanswered items, and export a cited response draft. Reuse `backend/app/playbooks/rfp.py` and source anchors.
2. **Commercial exception queue:** route below-floor margin, unusual discount, stale price, missing price, or unsupported claim to the right approver; preserve the decision with the quote version.
3. **Deal follow-up signals:** show missing customer inputs, expiring price validity, stale evidence, approvals awaiting action, and quote expiry. Send external notifications only through a configured tenant connector and its permission policy.
4. **Renewal and expansion view:** after ERP/CRM integration, surface approaching renewals and approved cross-sell candidates with evidence. This is a later phase because contract data and consent must be reliable first.

## 5. Data and service design

### Core entities

| Entity | Purpose and key rules |
|---|---|
| `Account` / `Opportunity` | Tenant-scoped CRM references, owner, collaborators, stage, dates, currency, and optimistic version. External IDs unique within tenant and connector. |
| `Requirement` / `RequirementEvidence` | Atomic customer need, source anchor, priority, acceptance criterion, coverage state, reviewer, and version. Preserve original text. |
| `SolutionVersion` / `SolutionComponent` | Immutable approved bill of materials candidate and dependency decisions; links to catalog products and provider SKUs. |
| `ProviderSkuMap` | Reviewed mapping of catalog product to provider service, SKU, meter, region, billing mode, effective interval, and status. |
| `PriceObservation` | Provider or ERP source response metadata, request fingerprint, rate/tier, unit, currency, effective/retrieved/expiry times, entitlement scope, and raw-response checksum; encrypt or restrict commercial payload. |
| `Quote` / `QuoteVersion` / `QuoteLine` | Quote identity and immutable versions. Lines reference observations, quantity, usage estimate, arithmetic and assumption records. Versions have draft/review/approved/issued/expired states. |
| `CommercialPolicyVersion` / `ApprovalDecision` | Versioned floor, discount, markup, tax, FX, and sign-off rules; reviewer, timestamp, rationale, and signed decision. |
| `Claim` / `ClaimEvidence` | Competitive or proposal statement with citation, publication and review dates, scope, validity, approval status, and revocation. |
| `IntegrationSyncRun` | Per-tenant ERP/CRM connector checkpoint, idempotency key, remote ID, status, error class, and retry history. |

Add migrations in `backend/app/db/migrations.py` with RLS, foreign keys, bounded indexes, unique tenant-scoped external IDs, and data backfill where applicable. Preserve existing document, catalog, workflow, and audit tables. Do not store large provider responses or generated files in graph edges.

### Pricing contract

Normalize provider responses into a versioned internal `PriceObservation`, while retaining the raw source and provider-specific parser version for audit. Required dimensions: provider, service/SKU/meter, region, tenancy/OS where relevant, billing mode, unit of measure, tier boundaries, currency, rate, effective period, quantity constraints, purchase/contract term, tax inclusion, rate type (`public`, `partner`, `customer_contract`), and eligibility. Use `Decimal` and explicit rounding policy at line and total levels. A missing dimension is a validation failure, not a zero-dollar line.

The commercial calculator takes an immutable observation plus a policy version and usage assumptions. It produces cost, sell price, discount, margin, taxes where configured, and total in a named currency. FX conversion requires an identified provider, timestamp, rate, and policy. Show estimated usage and excluded charges prominently. A quote snapshot never silently refreshes; repricing creates a new version and may require reapproval.

Cache public prices by complete provider dimensions and parser version, with TTL and stale status. Partition sensitive observations by organization and entitlement. Rate-limit, retry with backoff, and circuit-break provider calls. Failure modes are explicit: unavailable, unsupported, stale, ambiguous SKU, or permission denied. Never substitute another region, SKU, pricing term, or provider without review.

### Four CSP pricing API adapters

Implement a backend `PricingProvider` protocol with discovery, exact SKU resolution, rate retrieval, pagination, and health/capability reporting. Deliver all four adapters, starting with the provider most relevant to the pilot tenant and a small, reviewed SKU set. Each adapter has its own credential/entitlement configuration, rate limit, retry policy, provider fixture suite, and mapping table. Provider prices are inputs to the quote calculator; the ERP and commercial policy determine customer selling terms.

| Provider | Planned official API path | Adapter requirements |
|---|---|---|
| **Huawei Cloud** | Customer Operation Capabilities: pay-per-use `POST /v2/bills/ratings/on-demand-resources` and yearly/monthly `POST /v2/bills/ratings/period-resources/subscribe-rate`. | Confirm partner/customer authorization and market; resolve service/resource/specification/region and usage parameters; distinguish website amount, discounts, and eligible transaction price. |
| **AWS** | Price List Query API (`GetServices`, `GetAttributeValues`, `GetProducts`) using `boto3`; Bulk API when catalog-wide synchronization becomes more efficient. | Resolve service code, SKU, location, OS, tenancy, operation, offer term, unit and tier; paginate; distinguish public catalog from private agreements. |
| **Microsoft Azure** | Retail Prices API `GET https://prices.azure.com/api/retail/prices`. | Apply exact service/SKU/region/price-type filters; follow `NextPageLink`; retain meter, tier and reservation terms; mark public retail rate as distinct from contract rate. |
| **Google Cloud** | Cloud Billing Catalog API for public services/SKUs/pricing; Cloud Billing Pricing API for billing-account-specific prices when authorized. | Enable API and configure credentials; process SKU pagination, regions, tiered rates, display quantity, effective time and currency; keep account-specific data tenant private. |

Shared acceptance: an adapter must either return a fully dimensioned `PriceObservation` or an explicit unsupported/ambiguous/unavailable result. Test exact product matching, pagination, tiers, currency, price freshness, throttling, and provider response changes before enabling a SKU family for customer quotes. Recheck API availability, quotas, entitlements, and request fields during each implementation spike.

### Firecrawl and Exa MCP workstreams

Extend `backend/app/mcp/servers.py`, `sandbox.py`, `store.py`, `registry_bridge.py`, and the integrations API/UI to register **Firecrawl** and **Exa** per tenant. Use the existing allowlist, credential encryption, transport isolation, SSRF controls, timeouts, result size limits, and audit trail. Pin or otherwise control server versions if using local packages; evaluate hosted MCP transport against enterprise data residency and vendor terms before enablement.

- **Exa MCP:** discover candidate vendor documentation, competitor announcements, and product pages. Return URLs, titles, snippets, publication dates when available, and query metadata. It is the discovery step for competitive research, not an approved factual source by itself.
- **Firecrawl MCP:** fetch, crawl, and extract the selected pages into bounded, attributed content. Enforce allowed hosts, crawl depth/page/byte limits, deduplication, tenant budgets, and change detection. Send the extracted content through the existing document/source review flow; default to draft for commercial claims.
- **Research workflow:** Exa discovery → source selection → Firecrawl extraction → document/version record → citation and freshness check → human approval of a reusable claim → battle card or proposal use. Preserve the original URL, retrieval time, content hash, access classification, and reviewer. A tool failure or stale source leaves the claim unverified.
- **Pricing MCP:** expose backend read operations such as `search_products`, `get_price`, and `compare_pricing` only after the provider services and authorization checks exist. The tool must take `ToolContext` tenant scope from the server, return sanitized observations, and never issue or approve quotes.

### Google Sheets API and MCP workstream

Use the **Google Sheets API** for deterministic export of approved quote versions, comparison tables, and manager analysis. Create spreadsheets from tenant-owned templates; write values with `spreadsheets.values.batchUpdate` and format with `spreadsheets.batchUpdate`. The backend remains the source of quote totals, discounts, and approval status. Every sheet includes quote version, price observation IDs, currency, assumptions, and generated-at time; edits in Sheets do not silently alter the approved quote.

Support a tenant service account for shared team-owned sheets and per-user OAuth where access to a user's Drive is required. Store tokens encrypted and tenant-scoped, request minimal scopes, enforce destination allowlists and export authorization, and record the spreadsheet ID in the quote audit trail. Add a Google Sheets MCP integration for scoped read and draft-sheet operations; approved quote export still goes through the backend API and its policy checks. Add a later reviewed import path only if there is a real need for spreadsheet-edited assumptions.

### ERP/CRM boundary

Define an `ErpCrmAdapter` around accounts, opportunities, contract terms, customer-specific costs, quote handoff, and status reconciliation. Begin with read-only import and explicit field ownership. Use a transactional outbox/idempotency key for approved writeback so retries cannot create duplicate orders or quotes. Resolve conflicting edits with source-of-truth rules; never overwrite the ERP's commercial values from an AI draft.

### Evidence and graph

Extend existing `ProductEdge` and context links only for stable, reviewed relations such as `requires`, `integrates_with`, `alternative_to`, and `satisfies`. Keep account, opportunity, price, and quote records in relational tables and join them when rendering a scoped graph lens. All traversals have tenant, workspace, approval, hop, and result limits. Evidence links carry source ID, page/section anchor, version, access label, and validity. Revalidate source access on export, not only when drafting.

## 6. Workflow and APIs

Build typed FastAPI services under `backend/app/opportunities/`, `backend/app/pricing/`, `backend/app/quotes/`, and `backend/app/commercial/`; expose them through `backend/app/api/routes/`. Extend `backend/app/workflows/` with handlers for extraction, requirement review, solution validation, price fetch, calculation, approval, export, and CRM/ERP handoff. Tasks must be idempotent, bounded, retryable, observable, and safe after lease loss. Use the existing `Principal` and tenant-scoped session at each execution.

Suggested API surface, following repository route conventions:

```http
POST /api/opportunities
GET  /api/opportunities?cursor=&limit=
GET  /api/opportunities/{id}
POST /api/opportunities/{id}/requirements/import
PATCH /api/opportunities/{id}/requirements/{requirement_id}
GET  /api/opportunities/{id}/coverage
POST /api/opportunities/{id}/solutions
POST /api/opportunities/{id}/quotes
GET  /api/quotes/{id}/versions?cursor=&limit=
POST /api/quotes/{id}/reprice
POST /api/quotes/{id}/submit
POST /api/quotes/{id}/approve
POST /api/quotes/{id}/issue
GET  /api/quotes/{id}/export
GET  /api/workflows/{run_id}
```

All mutations use Pydantic schemas with bounded inputs, server-derived tenant identity, authorization checks, audit records, and idempotency keys where retries are likely. State transitions use database transactions and optimistic locking. Lists are paginated. Quotes and exports are restricted to opportunity participants and authorized managers. Approval requires separation of duties for policy exceptions.

## 7. Delivery phases and exit gates

Each phase ends with tests, migration review, access checks, telemetry, and a working user path. Feature flags enable controlled tenant pilots and rollback.

| Phase | Deliverable | Exit gate |
|---|---|---|
| **0 — Baseline and tenant controls** | Inventory current deployment and data; define roles, account assignments, RLS posture, retention, data classifications, tenant quotas, SLOs, and connector secrets policy. | Two-tenant isolation tests cover API, worker, cache, graph, search, export, and MCP paths; production fails closed when RLS is absent. |
| **1 — Opportunity and coverage** | Tenant-scoped account/opportunity records; editable requirement extraction; source anchors; coverage matrix and review UI. | A real RFP can be imported, corrected, assigned, and checked for uncovered mandatory items with no cross-tenant leakage. |
| **2 — Catalog-to-SKU mapping** | Reviewed provider SKU maps, dependency resolution, product lifecycle gates, and a versioned solution bill of materials. | A solution engineer can resolve the pilot workload, identify every required component, and explain each mapping. |
| **3 — Pricing foundation** | One provider adapter, observation store, cache, unit/tier normalization, freshness policy, failure states, and exact-price preview. | Golden provider fixtures reproduce expected rates and reject mismatched units, regions, terms, and ambiguous products. |
| **4 — Commercial quote MVP** | ERP/CRM read adapter or controlled commercial import; versioned policies; deterministic quote lines; approvals; immutable versions; export. | Pilot quote lines and totals recompute exactly from saved inputs, pass margin/discount policy, and cannot issue with unresolved mandatory requirements or stale rates. |
| **5 — Enterprise integration and scale** | Writeback outbox, tenant quotas/fair scheduling, dashboards, alerting, operational runbooks, restore drill, and load tuning. | Retries do not duplicate handoffs; target concurrency and latency SLOs hold across several tenants; restore and audit reconstruction succeed. |
| **6 — Four-provider comparison** | Complete Huawei, AWS, Azure, and Google Cloud adapters, SKU equivalence review, and normalized cross-provider comparison. | Each provider passes contract fixtures; comparison includes equivalent components, explicit exclusions, contract/public price labels, source and price freshness. |
| **7 — Research and spreadsheet integrations** | Exa MCP discovery, Firecrawl MCP extraction/crawl, reviewed battle-card claims, Google Sheets API export and restricted MCP tools. | Two-tenant isolation and quota checks pass; research is cited and reviewed; sheet values exactly match the approved quote version. |
| **8 — Sales intelligence** | RFP response automation, follow-up signals, renewal/expansion recommendations, management analytics. | Recommendations are access-controlled, supported by current account data and evidence, and measurable against sales outcomes. |

### Pilot definition

Use one tenant, one real sales owner, one solution engineer, one commercial approver, and one provider. Quote a workload with compute, storage, network/public access, and backup. Show the requirement coverage matrix, bill of materials, price source and effective time, usage assumptions, taxes/exclusions, margin policy result, reviewer decision, and customer-safe export. Then repeat with a second tenant to prove isolation. The four-provider comparison, Firecrawl, Exa, and Google Sheets have explicit later gates; they remain in the committed target architecture.

### Measures of effectiveness

Track requirement coverage rate and unresolved gap count; quote cycle time and human edit time; price match and stale-rate rejection rate; quote reproducibility; approval turnaround; unsupported claim rate; cross-tenant authorization failures; provider/tool spend per opportunity; queue wait and completion time; p95 API latency; and CRM/ERP handoff success. Set targets from the pilot baseline before broad rollout rather than inventing percentages now.

## 8. Verification and operational requirements

- Add unit tests in `backend/tests/` for every feature: parsing and validation, tenant and opportunity permissions, SKU mapping, tier/usage/FX/tax arithmetic, policy thresholds, state transitions, retries, idempotency, and export redaction. Include adversarial and two-tenant integration cases.
- Use provider contract fixtures with recorded, sanitized responses; keep live provider calls in a separate credentialed smoke suite. Compare generated quote totals to independent known examples and ERP-approved commercial values.
- Run `python scripts/verify_project.py`, relevant backend tests, Python syntax compilation, and frontend `tsc -b` for each code phase. Update Graphify after every code edit per workspace rules. A documentation-only revision does not change the code graph.
- Audit every retrieval of customer data, price observation, policy version, tool call, approval, reprice, issue, export, and writeback. Store enough inputs and version IDs for reconstruction while excluding secrets and unnecessary customer text from logs.
- Define tenant-specific retention and deletion behavior for accounts, documents, quote versions, provider responses, exports, backups, and audit records. Make legal hold explicit when required by a tenant's policy.
- Use tracing and metrics by tenant and workflow without exposing customer content in shared telemetry. Alert on expired rates, stalled jobs, provider failures, approval backlog, unusual spend, RLS posture, and repeated authorization denials.
- Size connection pools from database limits across **all** API and worker replicas. Benchmark HNSW recall/latency with tenant filters; add indexes based on real queries. Stream document processing and model output; paginate lists and cap graph traversals and research payloads.

## 9. Decisions to confirm during Phase 0

These are integration facts that the repository cannot determine: the primary ERP/CRM and its write authority; the first provider and regions/SKU families; tax jurisdictions and whether prices include tax; contract/partner pricing rights; quote legal wording and validity; approval thresholds and separation of duties; data residency and retention by tenant; and target concurrency/SLOs. Record each as a decision with an owner before its dependent phase begins.

## Reference documentation checked for adapter planning

- [Huawei Cloud pay-per-use price inquiry](https://support.huaweicloud.com/intl/en-us/api-oce/bcloud_01001.html)
- [AWS Price List API](https://docs.aws.amazon.com/aws-cost-management/latest/APIReference/)
- [Azure Retail Prices API](https://learn.microsoft.com/en-us/rest/api/cost-management/retail-prices/azure-retail-prices)
- [Google Cloud Billing Catalog API](https://docs.cloud.google.com/billing/v1/how-tos/catalog-api)
- [Google Cloud Billing Pricing API](https://docs.cloud.google.com/billing/docs/reference/pricing-api/rest)
- [Firecrawl MCP server documentation](https://github.com/firecrawl/firecrawl-docs/blob/main/mcp-server.mdx)
- [Exa MCP server documentation](https://github.com/exa-labs/exa-mcp-server/blob/main/README.md)
- [Google Sheets API reference](https://developers.google.com/workspace/sheets/api/reference/rest)
