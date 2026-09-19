# Project Plan: Solution Engineering Knowledge Workspace

Status: **proposed (rev 2)**, 2026-09-19. Supersedes `docs/ROADMAP.md` Phases 6-10 where they conflict.

Rev 2 incorporates the decided parameters below. The headline change: the corpus is small, so
distributed-systems work is cut and the effort moves to **graph quality and catalog freshness**,
which is where quality will actually be won or lost.

---

## 0. Decided parameters

| Question | Decision | Consequence |
|---|---|---|
| Deployment model | **Shared multi-tenant** | Row-level security from day one; isolation tests permanent |
| Catalog scope | **Own products and resold third-party products** | `vendor` and `source_of_truth` on every product; vendor collateral freshness is the hard problem |
| Collateral ownership | **Single owner (you), for now** | Governance stays lightweight: review dates and a dashboard, no approval workflow engine |
| CRM integration | **Out of scope** | Accounts and opportunities are native records; CSV import/export only |
| Scale, year one | **~20 products, ~50 documents, ~50 users** | Small. See section 2 |
| Call recording and transcription | **Out of scope** | No audio or video ingestion. Discovery input is typed or pasted notes only |

---

## 1. What this is

A knowledge workspace for pre-sales and post-sales solutions engineering: the product portfolio,
collateral, and account history become one linked, searchable, citable graph, plus an AI that
composes **multi-product solutions** grounded in that graph.

The scenario it must handle end to end:

> A customer needs cloud infrastructure, but also has an on-prem server problem and wants video
> conferencing. An SE asks what combination we can offer and gets a bundle, the reasons each
> product fits, known integration gaps, the reference architecture, comparable past deals, and a
> citation for every claim.

What each existing tool gives, and what must be added:

| Need | Obsidian | NotebookLM | This app adds |
|---|---|---|---|
| Products and how they relate | Untyped links | Nothing | **Typed** graph: integrates-with, requires, conflicts-with |
| Answers from real collateral | Nothing | Cited answers | Answers scoped to **current, approved** collateral |
| Composing a solution | Nothing | Nothing | Requirement to capability to product matching |

## 2. What the size of this changes

20 products, 50 documents, and 50 users is a **small corpus with a high accuracy bar**. That
inverts the usual priorities:

- **Cut entirely:** read replicas, table partitioning, a dedicated vector database, a distributed
  queue, aggressive caching layers, and sharding. One PostgreSQL instance with pgvector will serve
  this corpus comfortably for years. Revisit only if measurement contradicts that.
- **Keep, but simplify:** background processing. Bulk upload still must not block a request, but
  FastAPI background tasks or a single lightweight worker is sufficient. No Redis, no Celery cluster.
- **Where the risk actually sits:** with 50 documents, retrieval will rarely fail to find the right
  passage. Bad answers will come from **a wrong or missing graph edge**, **stale vendor collateral**,
  or **thin coverage of a product**. So the investment goes into catalog curation, evidence on
  edges, freshness tracking, and evaluation — not infrastructure.
- **Multi-tenancy at 50 users** is not about load, it is about **confidentiality**: customer
  material must not leak between accounts, and resold-vendor material may carry its own restrictions.
  RLS earns its place for correctness, not scale.
- **Feasible consequence:** the golden-scenario and labeled question sets can plausibly cover a
  large share of real usage. Evaluation is unusually cheap here. Use that.

## 3. Core principles

1. **Never invent a capability.** If collateral does not support a claim, say so.
2. **Every claim carries a citation and a date.** Pricing and compatibility go stale.
3. **Approved vs draft is first-class.** Customer-facing output uses approved collateral only.
4. **The graph is typed.** "Related" is useless; "requires" and "conflicts with" are actionable.
5. **Own vs resold is always visible.** An SE must never be unsure who owns a product's roadmap or
   support path.
6. **Customer data is confidential by default.**
7. **Ingested content is untrusted input.** Documents are data, never instructions.
8. **AI proposes, the SE decides.**
9. **Measured, not vibes.** Retrieval and recommendations are evaluated against labeled sets.

---

## 4. Phase map

| Phase | Name | Outcome | Depends on |
|---|---|---|---|
| 0 | Foundation and security baseline | Multi-tenant, authenticated, auditable skeleton | — |
| 1 | Ingestion | Bulk upload, many formats, background, safe | 0 |
| 2 | Hybrid retrieval | Filtered, permission-aware, measurable search | 1 |
| 3 | Grounded answers | Cited answers that refuse when unsupported | 2 |
| 4 | Product catalog and typed graph | Portfolio modeled, own and resold | 1 |
| 5 | Solution composer | The headline feature: requirements to bundles | 3, 4 |
| 6 | Pre-sales workflows | RFP answering, proposals, battlecards | 5 |
| 7 | Post-sales workflows | Install base, runbooks, QBR, expansion | 5 |
| 8 | Notes, linking, and authoring | SE-authored knowledge in the same graph | 2 |
| 9 | Freshness and feedback loop | Win/loss, staleness, gaps, contradictions | 6, 7 |
| 10 | Hardening and integrations | SSO, document-source sync, capacity checks | 9 |

A phase is not done until its testing and security items pass.

---

## Phase 0: Foundation and security baseline

Structural, and the one thing genuinely painful to retrofit, since tenancy touches every query.

**Scope**
- Tenancy: `organization` to `workspace` to resources. Every table carries `org_id`.
- PostgreSQL **row-level security**, enforced by the database rather than by remembering a `WHERE`
  clause. The application connects as a non-superuser role with RLS forced.
- AuthN: email and password or OIDC; session or JWT handling with revocation.
- AuthZ: roles `admin`, `solutions_engineer`, `sales`, `viewer`, plus per-account access grants.
- Sensitivity labels on every resource: `public`, `internal`, `confidential`, `customer_data`,
  plus `vendor_restricted` for resold material under NDA or partner terms.
- Append-only audit log: who viewed or exported which customer or vendor material, and when.
- Secrets via environment or a secret manager only, enforced by CI secret scanning.
- Structured logging with request IDs and a PII redaction helper.
- Error taxonomy that never leaks internals to the client.

**Testing**
- CI on every PR, with a coverage floor.
- **Tenant isolation tests, permanent and never skipped:** a user in org A gets 404 (not 403) for
  org B's resources, on every endpoint. Every new endpoint adds a case.
- Authorization matrix: each role against each endpoint, expected allow or deny.
- Dependency vulnerability and secret scanning in CI.

**Exit:** a second organization cannot detect the first's existence through any endpoint, and the
authorization matrix passes with no skipped rows.

---

## Phase 1: Ingestion

**Scope**
- Bulk upload: many files at once, folder drop, plus URL and pasted text.
- Formats: PDF, DOCX, **PPTX** (where SE collateral usually lives), XLSX, TXT/Markdown, HTML.
  OCR for scanned PDFs.
- Background processing with per-job status, retry with backoff, and a failed state. A single
  worker process is sufficient at this corpus size; no distributed queue.
- Citation anchors preserved: page, slide number, sheet and cell range, heading path.
- Deduplication by content hash; versioning when a document is re-uploaded.
- Document metadata, all required at upload: source type, **vendor**, **own or resold**, products
  referenced, **approval state**, **valid-until date**, sensitivity label.

**Security**
- File type and size validated by content sniffing, not extension.
- Malware scanning before parsing; parsing in a resource-limited sandbox with timeouts.
- XXE and zip-bomb protections for archives, OOXML, and HTML.
- URL ingestion through an **SSRF-safe fetcher**: private IP ranges, cloud metadata endpoints, and
  redirects to internal hosts all denied.
- **Prompt-injection containment:** ingested text is demarcated as untrusted data in every prompt;
  the system prompt states that document content can never issue instructions; content-derived text
  never gains tool access. Instruction-like passages are flagged for review. This matters
  specifically because customer RFPs and third-party vendor PDFs are ingested routinely.

**Testing**
- Fixture corpus per format, including one deliberately malformed file per type.
- Golden extraction tests: page and slide anchors resolve to the right location.
- Chunk determinism tests, so evaluation stays comparable across runs.
- Bulk test at 10x the real corpus (500 documents): the queue drains, memory is flat, statuses correct.
- Injection corpus: documents containing instruction-like text produce no behavior change.

**Exit:** the full document set ingests unattended, every failure is individually explainable and
retryable, and the injection corpus is inert.

---

## Phase 2: Hybrid retrieval

**Scope**
- Vector (pgvector) plus full-text (tsvector) with Reciprocal Rank Fusion. Deterministic.
- **Filtered retrieval, required not optional:** by product, vendor, account, approval state,
  freshness, sensitivity, and document type. Filters apply before fusion.
- Permission-aware retrieval: candidates are filtered by the caller's grants at query time, so a
  chunk the user may not read never reaches the model.
- `POST /search` debug endpoint exposing scores and fusion inputs.

**Testing**
- Labeled set of 50+ real SE questions with the correct passage marked. At this corpus size that is
  meaningful coverage, not a token sample.
- Compare vector-only, keyword-only, and hybrid; record the baseline in writing before tuning.
- Permission tests: a restricted chunk never appears in results or in a generated answer.
- Latency budget: p95 under 500 ms. Expect this to be met trivially; record it anyway as a
  regression tripwire.

**Exit:** a written baseline exists and permission filtering has a test that fails loudly if removed.

---

## Phase 3: Grounded answers

**Scope**
- Generation behind a provider interface. Strict grounded prompt: answer only from context and
  **state when the context is insufficient**.
- Citations extracted to a structured field, clickable back to page or slide.
- Every answer shows the **freshness, approval state, and vendor** of its sources.
- Conversation history, per-answer source list, source toggling.
- Cost controls: per-org token budgets, per-user rate limits, streaming responses.

**Testing**
- Refusal set: questions the corpus genuinely cannot answer must be declined, not guessed.
- Citation accuracy hand-scored on a fixed question set.
- Prompts versioned like code; the regression suite runs on every prompt or model change.
- Adversarial set: questions phrased to elicit unsupported pricing or competitive claims.

**Exit:** citations resolve correctly on the labeled set, and unsupported questions are refused.

---

## Phase 4: Product catalog and typed graph

Where this stops being a notes app. Given the decision to carry **both own and resold products**,
provenance is modeled from the start rather than bolted on.

**Scope**
- **Product entities:** name, **vendor**, **own or resold**, category, tier, deployment model
  (cloud / on-prem / hybrid), licensing model, target segment, lifecycle status (GA, EOL, roadmap),
  prerequisites, support path, and links to collateral.
- Resold-specific fields: partner tier, margin band if tracked, **who owns support and escalation**,
  contract or NDA constraints on what may be shared externally, and **upstream source of truth**
  (the vendor page or datasheet the record derives from).
- **Capability taxonomy:** a controlled vocabulary of what products do ("identity federation",
  "site-to-site VPN", "call recording"). Products map to capabilities; customer requirements map to
  the same vocabulary. This join is what makes matching possible, and with 20 products it is
  genuinely achievable by hand in days, not months.
- **Typed relationships**, each with evidence and a confidence value:
  `integrates_with`, `requires`, `conflicts_with`, `replaces`, `bundles_with`, `alternative_to`,
  `migrates_to`. Cross-vendor edges (own product integrates with resold product) are the
  commercially interesting ones and deserve the most curation effort.
- Graph visualization: portfolio view, and a neighborhood view around one product or account.
- Manual curation UI plus AI-suggested edges that you accept or reject; every suggestion cites the
  document implying it.
- Reference architectures as first-class entities composing several products.

**Testing**
- Schema validation: no orphan capabilities, no edge without evidence.
- Graph integrity: cycle detection on `requires`; contradiction detection (a bundle containing a
  `conflicts_with` pair).
- Coverage report: every product has at least one capability, one document, and one edge.
- Curation workflow: accepted suggestions become edges; rejected ones do not reappear unchanged.

**Exit:** all 20 products are modeled with capabilities and edges, and the graph answers "what does
X require and what does it break" without a human reading a datasheet.

---

## Phase 5: Solution composer

The headline feature. Everything before it exists to make it trustworthy.

**Scope**
- **Requirement capture:** paste discovery notes, an RFP extract, or typed call notes; the app extracts
  discrete requirements, pain points, and constraints (budget, compliance, timeline, incumbent
  vendors, deployment preference). The SE edits the extracted list.
- **Requirement to capability mapping**, shown explicitly so it can be corrected.
- **Bundle generation:** candidate sets scored on requirement coverage, internal compatibility (no
  `conflicts_with` edges), constraint fit, and evidence strength.
- Each bundle shows what it covers, **what it does not cover**, prerequisites, integration risks, a
  reference architecture if one exists, own vs resold composition, and citations throughout.
- **Gap report:** requirements nothing satisfies. Valuable output, not failure. Feeds Phase 9.
- Alternatives and trade-offs: cheaper, faster to deploy, more scalable, fewer vendors.
- Multi-domain by design. The cloud plus on-prem plus video conferencing case is the acceptance test.
- Export to a proposal draft.

**Testing**
- **Golden scenario set:** 20+ real past deals with known-good solutions. Measure whether the
  composer proposes them; track the score across releases.
- Negative tests: unsatisfiable requirements produce gaps, never invented products.
- Constraint tests: an on-prem-only customer never receives a cloud-only bundle.
- Conflict tests: a known-incompatible pair is never proposed together.
- Blind comparison of composer output against an SE's manual answer.

**Exit:** on the golden scenarios the composer matches or beats the manual answer on coverage, and
never proposes a conflicting pair.

---

## Phase 6: Pre-sales workflows

**Scope**
- **RFP and security questionnaire answering:** ingest the questionnaire, draft cited answers from
  approved collateral, flag low-confidence answers for review, export in the original format. Often
  the single largest time saving available.
- **Proposal and SOW drafting** from a chosen bundle using approved templates and boilerplate.
- **Battlecards and objection handling**, cited, with competitive claims drawn only from approved
  sources.
- **Discovery question generator** based on what is not yet known about the account.
- **Account workspace:** all material for one opportunity in one scope, with its own chat.
- Native account and opportunity records with CSV import and export, since CRM sync is out of scope.

**Security**
- Customer material is `customer_data` by default, granted per account.
- Exports and shares are audited and restrictable by role.
- **Resold-vendor constraints enforced at export:** material marked `vendor_restricted` cannot enter
  a customer-facing document without an explicit override, which is logged.

**Testing**
- Questionnaire regression set with human-graded answers.
- Template rendering tests across output formats.
- Approval-state enforcement: draft or restricted collateral never reaches an export.

**Exit:** a real RFP is answered end to end through a review queue, with no unapproved or restricted
content in the export.

---

## Phase 7: Post-sales workflows

**Scope**
- **Install base per account** as graph nodes, so expansion and compatibility questions are answerable.
- **Implementation runbooks** and configuration baselines per product combination.
- **Known issues and escalation history**, searchable, so recurring problems are recognized on sight.
  For resold products, record whether the escalation path is yours or the vendor's.
- **Troubleshooting assistant** grounded in runbooks, past cases, and vendor documentation.
- **QBR preparation:** adoption, open issues, gaps, and a recommended next step, cited.
- **Expansion signals:** given the install base graph, which adjacent products fit, and why now.
- **Renewal risk view:** open escalations, stale adoption, EOL products in the install base.

**Testing**
- Troubleshooting evaluation against past resolved cases as a labeled set.
- EOL propagation: marking a product end-of-life flags every affected account. Especially important
  for resold products, whose EOL dates are set by someone else.

**Exit:** for a sample account the app produces a QBR pack and an expansion recommendation an SE
would send with light edits.

---

## Phase 8: Notes, linking, and authoring

SE-authored knowledge belongs in the same graph. It sits here, not first, because the catalog and
composer concentrate the value.

**Scope**
- Markdown editor with live preview; templates for discovery notes, solution briefs, runbooks, and
  post-mortems.
- `[[wikilinks]]` including links to product and account entities, with autocomplete and rename-safe
  references; backlinks and unlinked mentions.
- Notes indexed like any other source, so answers can cite an SE's own note.
- Tags, folders, frontmatter properties, daily notes, command palette.
- **Tribal knowledge capture:** prompt the SE to write up a deal or a workaround and link it to the
  products involved. With only 50 documents, SE-authored notes will quickly become a large share of
  the corpus, and they are where undocumented integration knowledge lives.
- Version history with attribution.

**Testing**
- Link integrity across renames and deletes.
- Reindex-on-save correctness and debounce behavior.
- Notes respect sensitivity labels and account scoping like any other resource.

**Exit:** an SE writes a solution brief, links it to three products, and it becomes retrievable and
citable in the composer.

---

## Phase 9: Freshness and feedback loop

With a single collateral owner and resold products whose documents change without warning, this is
the phase that keeps the system trustworthy. A stale knowledge base people still trust is worse than
no knowledge base.

**Scope**
- **Freshness governance, deliberately lightweight** (single owner, no approval workflow engine):
  every item has a review date; overdue items are flagged, down-ranked in retrieval, and listed on
  one dashboard.
- **Vendor collateral monitoring for resold products:** record the upstream source URL, re-check it
  on a schedule, and flag when the upstream document changes or the local copy passes its
  valid-until date. This is the highest-value automation in the phase, because third-party
  datasheets change without notice.
- **Win/loss capture:** record which bundle was proposed and the outcome; feed results into scoring.
- **Coverage and gap dashboard:** capabilities customers ask for that the portfolio lacks, questions
  the app failed to answer, products with thin collateral.
- **Contradiction detection** across sources, for example two datasheets disagreeing on a limit.
- Usage analytics: most-cited assets, most-asked questions, unanswered queries.
- Continuous evaluation on a schedule, with results tracked over time.

**Testing**
- Backtesting: does outcome-weighted scoring improve golden-scenario results, or merely overfit? At
  20 products, overfitting is a real risk, so hold out scenarios.
- Staleness rules verified against seeded dates.
- Contradiction detection measured for precision; a noisy detector gets ignored.

**Exit:** a dashboard worth opening weekly, and evaluation scores tracked across releases.

---

## Phase 10: Hardening and integrations

Reduced from the original plan: with 50 users and 50 documents, most scale engineering is not
justified. What remains is access management, content sync, and proving the limits.

**Scope**
- **SSO (SAML/OIDC) and SCIM provisioning**, enforced MFA, session policy. At 50 users this is about
  offboarding correctness and access review, not convenience.
- Sync from existing document sources (SharePoint, Drive, Confluence) with incremental updates and
  permission mapping. This matters more than CRM here, because it is where collateral already lives.
- Compliance posture: retention and deletion policies, access review, encryption at rest and in
  transit, key rotation, data residency if required by a customer.
- **Capacity verification, not capacity engineering:** load test at 10x projected corpus and
  concurrency, publish the measured limits, and stop there. Add infrastructure only when a
  measurement demands it.
- Backup and **tested restore drills**. Restore is tested, not assumed.
- Penetration test or third-party security review before significant customer data accumulates.
- Public API and webhooks if integration demand appears.
- Desktop or PWA packaging only if field offline use is real.

**Exit:** documented capacity limits, a passed security review, and a tested restore path.

---

## 5. Testing strategy (all phases)

| Layer | Covers | Runs |
|---|---|---|
| Unit | Chunking, parsing, scoring, graph rules | Every commit |
| Integration | API, database, RLS behavior | Every PR |
| Tenant isolation | Cross-org access on every endpoint | Every PR, never skipped |
| Authorization matrix | Role by endpoint expectations | Every PR |
| Retrieval evaluation | Labeled question set, hit rate | Nightly, and before release |
| Generation evaluation | Citation accuracy, refusal behavior | Before any prompt or model change |
| Composer evaluation | Golden past-deal scenarios | Before release |
| Graph integrity | Cycles, contradictions, orphans, coverage | Every PR |
| Adversarial | Prompt injection, data exfiltration attempts | Nightly |
| Load and soak | Bulk ingestion, concurrent query, at 10x | Before release |
| Security scanning | Dependencies, secrets, SAST | Every PR |

Two standing rules: **pin prompts and models during any comparison**, and **record the baseline
before tuning**, or improvement cannot be distinguished from noise.

## 6. Security posture

| Risk | Control | Phase |
|---|---|---|
| Cross-tenant exposure | RLS plus permanent isolation tests | 0 |
| Over-broad internal access | Roles, per-account grants, sensitivity labels | 0, 6 |
| Confidential material in AI answers | Permission-filtered retrieval before generation | 2 |
| Prompt injection via uploaded documents | Untrusted-data demarcation, no tool access, flagging | 1 |
| SSRF via URL ingestion | Allowlist fetcher, private range denial | 1 |
| Malicious file parsing | Sandboxed parsing, content sniffing, archive limits | 1 |
| Leaked credentials | CI secret scanning, secret manager | 0 |
| Unapproved content reaching a customer | Approval state enforced at export | 6 |
| Vendor-restricted material disclosed externally | `vendor_restricted` label, logged override | 4, 6 |
| Untraceable disclosure | Append-only audit log | 0 |
| Model cost abuse | Per-org budgets and rate limits | 3 |
| Data loss | Tested restore, retention policy | 10 |

## 7. Scalability posture

Right-sized to roughly 20 products, 50 documents, and 50 users:

- One PostgreSQL instance with pgvector. No replicas, partitioning, or dedicated vector store.
- Background worker for ingestion so requests never block. No distributed queue.
- Retrieval filters push work into indexed columns before vector search.
- Cache embeddings and repeated generations, because model calls dominate cost, not compute.
- Providers behind interfaces so they stay swappable.
- Capacity assumptions written down and re-measured each phase. **Add infrastructure only when a
  measurement demands it**, and record the measurement that justified it.

## 8. Sequencing

**Why this order:** tenancy and security first because they are structural; ingestion and retrieval
next because everything reads from them; catalog and composer before the workflow phases, because
RFPs, proposals, and expansion advice are thin layers over the same matching engine.

**Do not build before Phase 5 ships:** collaboration, mobile apps, audio overviews, plugin system,
CRM integration.

**Out of scope entirely (decided):** call recording, audio or video ingestion, and transcription.
Discovery input enters as typed or pasted text.

**Highest-risk items, watch these:** capability taxonomy quality (Phase 4), cross-vendor edge
curation (Phase 4), and resold-collateral freshness (Phase 9).

## 9. Open questions

None outstanding. All questions from the previous revision are decided (section 0).