# Phase 4: Product Catalog and Typed Graph, as built

Implements `Project_Plan.md` **Phase 4 (Product catalog and typed graph)**: where this stops being a notes app. Carries both **own and resold products** with strict provenance, a controlled **capability taxonomy**, **typed graph relationships** with evidence and confidence, **reference architectures**, graph traversal algorithms for dependency and conflict analysis, and an **AI edge suggestion & curation workflow**.

---

## 1. Overview of Phase 4 Deliverables

| Plan Requirement | Plan Ref | Status | Where |
|---|---|---|---|
| Product entities (own & resold, vendor, category, tier, deployment, lifecycle, prerequisites, support path) | L213-215 | Done | `backend/app/db/models.py` (`Product`), `backend/app/catalog/models.py` |
| Resold-specific fields (partner tier, margin band, support owner, NDA constraints, source of truth URL) | L216-218 | Done | `Product.partner_tier`, `Product.support_owner`, `Product.source_of_truth_url`, etc. |
| Capability taxonomy (controlled vocabulary, products map to capabilities) | L219-222 | Done | `Capability`, `ProductCapability`, `backend/app/catalog/seeds.py` (18 capabilities) |
| Typed relationships (`integrates_with`, `requires`, `conflicts_with`, `replaces`, `bundles_with`, `alternative_to`, `migrates_to`) with evidence and confidence | L223-226 | Done | `ProductEdge` with check constraints and non-empty evidence enforcement |
| Graph visualization (portfolio view, neighborhood view around a product) | L227 | Done | `frontend/src/components/GraphExplorer.tsx`, `GET /graph/portfolio`, `GET /graph/neighborhood/{id}` |
| Curation UI & AI edge suggestion workflow (accept/reject, citations, rejection idempotency) | L228-229 | Done | `app/catalog/curation.py`, `POST /graph/suggest-edges`, `POST /graph/edges/{id}/approve`, `reject` |
| Reference architectures composing several products | L230 | Done | `ReferenceArchitecture`, `ReferenceArchitectureProduct`, 3 seeded blueprints |
| Graph integrity: cycle detection on `requires` | L234 | Done | `app/catalog/graph.py` (`detect_cycles_in_requires`) |
| Graph integrity: contradiction detection (bundle conflicts, requires+conflict contradictions) | L234-235 | Done | `app/catalog/graph.py` (`detect_contradictions`) |
| Coverage report: every product has >= 1 capability, >= 1 document, >= 1 edge | L236 | Done | `app/catalog/graph.py` (`compute_coverage`), `GET /graph/coverage` |
| "What does X require and what does it break" query | L239-240 | Done | `app/catalog/graph.py` (`query_product_impact`), `GET /graph/query` |
| 20 products modeled with capabilities and edges | L239 | Done | `app/catalog/seeds.py` (10 own products, 10 resold products, 25+ edges) |

---

## 2. Architectural Components

### A. Data Models & Migrations (`backend/app/db/`)
- **`models.py`**:
  - `Product`: Core catalog entity. Supports both in-house products and third-party resold products with dedicated governance columns (`partner_tier`, `margin_band`, `support_owner`, `contract_constraints`, `source_of_truth_url`).
  - `Capability`: Controlled taxonomy vocabulary with unique slugs per organization.
  - `ProductCapability`: M:N join table tracking product proficiency (`native`, `supported`, `via_integration`) and architectural notes.
  - `ProductEdge`: Directed/typed relationship between products. Enforces evidence requirement via SQL check constraints (`length(trim(evidence)) > 0`) and confidence values (0.0 to 1.0).
  - `ReferenceArchitecture` & `ReferenceArchitectureProduct`: Composable solution blueprints associating products with specific architecture roles (e.g., "Core Identity Provider", "Perimeter Gateway").
- **`migrations.py`**: Migration `0010_phase4_product_graph` adds the 6 tables, foreign keys with cascade deletions, unique constraints, and B-tree indexes for fast traversal.

### B. Graph Traversal & Integrity Engine (`backend/app/catalog/graph.py`)
- **Cycle Detection**: Depth-first search (DFS) with recursive back-edge detection on directed `requires` dependencies. Prevents circular dependencies in product deployment requirements.
- **Contradiction Detection**:
  1. *Direct Contradiction*: Product A declared as both requiring and conflicting with Product B.
  2. *Bundle Contradiction*: A reference architecture containing a pair of products linked with a `conflicts_with` edge.
  3. *Transitive Requirement Contradiction*: Product A transitively requires Product B, but Product A or one of its dependencies is marked as conflicting with B.
- **Impact Query Engine (`query_product_impact`)**:
  - Computes transitive prerequisite closures (all components needed to run product X with path and depth).
  - Computes all incompatibilities (direct conflicts, prerequisite conflicts, and downstream systems that would be broken by deploying product X).
  - Collects certified integrations and competitive/functional alternatives.
- **Coverage Audit (`compute_coverage`)**:
  - Validates that 100% of products have at least one capability, at least one linked collateral document, and at least one edge in the graph.
  - Detects orphan capabilities that have no mapped products.

### C. AI Edge Suggestion & Curation Workflow (`backend/app/catalog/curation.py`)
- **`EdgeSuggestionEngine`**:
  - Analyzes ingested document chunks for co-occurrences of catalog product names alongside linguistic relationship patterns (e.g., "requires", "prerequisite is", "integrates with", "incompatible with", "replaces", "alternative to").
  - Emits candidate suggestions with `is_ai_suggested=True` and `status=EdgeStatus.PENDING_REVIEW`, accompanied by cited evidence and confidence scores.
  - **Rejection Idempotency**: Edge suggestions previously rejected by an engineer are permanently stored with `status=EdgeStatus.REJECTED` and recorded in `blocked_signatures`. Re-running suggestion extraction will never regenerate rejected suggestions unchanged.

### D. API Layer (`backend/app/api/routes/catalog.py`)
- Full RESTful surface for products, capabilities, reference architectures, and graph queries:
  - `GET /catalog/products`: Filterable list of catalog products.
  - `GET /catalog/products/{id}`: Detailed product view including incoming/outgoing edges and reference architectures.
  - `GET /graph/portfolio`: Node-link payload for the visual canvas graph.
  - `GET /graph/neighborhood/{id}`: Focused 1-hop and 2-hop neighborhood of a product.
  - `GET /graph/query?product_id={id}`: Answer "what does product require and what does it break".
  - `GET /graph/integrity`: Automated cycle and contradiction audit.
  - `GET /graph/coverage`: Portfolio completeness audit report.
  - `POST /graph/suggest-edges`: Scan documents for implied candidate edges.
  - `POST /graph/edges/{id}/approve` & `POST /graph/edges/{id}/reject`: Curation actions.

---

## 3. Seed Catalog Summary (20 Products)

The catalog is seeded with 20 realistic, multi-domain enterprise products:

1. **Own Products (10)**:
   - *Apex Identity Broker* (Identity & Access, Cloud, GA)
   - *Aegis Zero Trust Gateway* (Cybersecurity, Hybrid, GA)
   - *Nova Cloud Storage* (Storage & Compute, Cloud, GA)
   - *Strata Observability Platform* (Observability, Cloud, GA)
   - *Nexus Service Mesh* (Networking, Hybrid, GA)
   - *Krypton Key Vault* (Security & Compliance, Hybrid, GA)
   - *Vanguard SIEM* (Cybersecurity, Cloud, GA)
   - *Prism API Gateway* (API & Integration, Cloud, GA)
   - *Helios Container Engine* (Compute & Containers, Hybrid, GA)
   - *Aether Messaging Bus* (Event Streaming, Cloud, GA)

2. **Resold Products (10)**:
   - *Okta Workforce Identity Cloud* (Okta, Premier Partner)
   - *Microsoft Entra ID* (Microsoft, Gold CSP)
   - *Palo Alto PA-Series Next-Gen Firewall* (Palo Alto Networks, Diamond Partner)
   - *Fortinet FortiGate UTM* (Fortinet, Expert Partner)
   - *Cisco Catalyst 9000 Switches* (Cisco, Gold Certified)
   - *AWS Direct Connect* (Amazon Web Services, Advanced Tier)
   - *Snowflake Data Cloud* (Snowflake, Elite Partner)
   - *Datadog Cloud Monitoring* (Datadog, Gold Partner)
   - *Pure Storage FlashArray* (Pure Storage, Elite Reseller)
   - *Zoom Phone & Meetings* (Zoom, Certified Partner)

3. **Reference Architectures (3)**:
   - *Secure Hybrid Cloud Foundation*
   - *Enterprise Zero-Trust SOC*
   - *Microservices Production Edge*

---

## 4. Exit Criteria Verification

- **20 Products Modeled**: Confirmed. 10 own products, 10 resold products with full governance attributes.
- **Coverage**: 100% of products have at least one capability, one linked collateral document, and at least one edge.
- **Integrity**: 0 cycles on `requires` edges; 0 contradictions in reference architectures.
- **Querying**: Graph answers "what does X require and what does it break" deterministically without manual datasheet consultation.
