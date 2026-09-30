# Deep Atlas continuation — 30 September 2026

## Confirmed operating scope

Public list prices only; no tax, discount, markup, or required contract-cost input. Sales records and authoritative writeback are internal to Deep Atlas. Provider mappings focus on Southeast Asia, including Huawei Manila. Separate quote author/reviewer duties and immutable quote versions remain enforced.

## Implemented in this continuation

- Restricted Google Sheets tools in the native tool registry and external MCP JSON-RPC surface: `mcp_google_sheets_read_sheet` and `mcp_google_sheets_write_draft`.
- Administrative sheet destinations use aliases, tenant-owned workspace IDs, spreadsheet IDs, a named tab, and explicit draft-write permission. Tool arguments cannot supply tokens, organization IDs, spreadsheet IDs, URLs, or ranges. Reads and writes cover at most 100 rows and 26 columns; writes are bounded to 32 KiB and use `RAW`. Responses are limited to 64 KiB and fenced as untrusted. Recorded quote export destinations cannot be overwritten by draft tools. Token scope, sales role, tenant/workspace checks, and sanitized auditing apply.
- Integration configuration UI for these workspace sheet destinations. Existing issued quote export and recovery paths are preserved.
- AWS, Google Cloud, and Huawei are connected to the existing reviewed-mapping capture endpoint alongside Azure. Provider responses must match provider/service/SKU/meter/region/billing mode before storage. Credentials are encrypted and tenant scoped, with no fallback to host AWS credentials. Captures store public rates and source-specific provenance.
- A tenant administrator can rotate or disable pricing credentials at `PUT /api/sales/pricing-credentials/{aws|gcp|huawei}`. These are stored in the existing tenant integration store, never returned to the model. Huawei capture requires an explicit `huawei_spec` whose core dimensions match the approved mapping. Static Huawei IAM tokens require rotation before expiry.
- New quote drafts require a zero-tax, zero-discount list-price policy and public observations. The API rejects incompatible policies and discounts. The calculator can compute list prices without commercial costs. Historical snapshots are preserved.
- Opportunity follow-up signals report missing mandatory requirements, pending approvals, and expiring/expired saved price inputs. Signals enforce opportunity participation and tenant scope, verify quote snapshot integrity, and include price source references. The quote UI displays these signals and refreshes them after draft creation or state transitions.
- Verification now runs frontend regression tests, fails for missing build tooling/dependencies, and rejects unexpected backend skips. Only the documented absence of a reachable PostgreSQL test database is accepted.
- Google credential exchanges and Sheets API calls have bounded network timeouts.

## Validation evidence

Baseline full verifier: **622 backend tests passed, 35 PostgreSQL tests skipped**, successful frontend production build.

Final verifier after the continuation: **647 backend tests passed, 35 necessary PostgreSQL skips; 22 frontend tests passed**. Python compilation, TypeScript/build, and Graphify integrity passed. Full output is recorded in [verification-final.log](../verification-final.log).

Corrective retries used: **0 of 7**. No failed test runs were suppressed or converted into passing tests. A Starlette/AnyIO deprecation warning remains informational.

The 35 skips all originate from the existing PostgreSQL fixture's `no reachable DATABASE_URL` condition. No PostgreSQL service, `psql`, or Docker executable was found in this workspace environment. SQLite tests exercise application isolation, but do not prove PostgreSQL RLS, pgvector, or production migration behavior.

## Remaining plan gates — not claimed complete

| Area | Remaining work or evidence |
|---|---|
| Production tenant controls | Run the PostgreSQL RLS/migration suite against PostgreSQL with pgvector using an isolated test database. Validate deployment roles and delayed worker authorization for sales workflows. |
| Solution bill of materials | Formal immutable solution entities, dependency completeness, reviewed evidence links, and production pilot coverage still need a dedicated pass. Quote snapshots already preserve their chosen mappings and quantities. |
| CSP production enablement | Real tenant credentials, reviewed Southeast Asia product/region families, live credentialed smoke checks, complete provider capability/discovery coverage, pricing refresh jobs/cache/backoff/circuit breakers, and source-response checksums remain. The capture wiring and offline contract fixtures do not establish live availability. |
| Four-provider comparison | Reviewed equivalence groups and a normalized comparison UI remain. Explicit unsupported results continue to apply to unsupported terms/tier families. |
| Research | Exa and Firecrawl remain available in code and plan. A durable discovery/extraction/source review/claim approval workflow and reviewed reusable battle cards remain. Tool results alone are not approved claims. |
| Enterprise operations | Tenant sales/research/export quotas, fair scheduling measurements, defined SLOs, load tests, restore/audit reconstruction drills, and operational dashboards require implementation or deployment evidence. |
| Sales intelligence | Follow-up signals are implemented. Management analytics, structured renewal records, evidence-backed expansion recommendations, and complete RFP response automation remain. Internal contract records will be needed before renewal intelligence can be truthful. |
| External ERP/CRM | Removed from scope by the user; no connector or external order creation is required. |

Do not mark the entire implementation goal complete solely because local tests pass. Keep these gates visible for the next continuation.

## Configuration notes

For new policies, post a version and currency to `/api/sales/policies`; zero tax/discount/margin defaults are enforced. Existing policies with nonzero adjustments cannot be used for new drafts.

Provider secrets:

- AWS: JSON containing `access_key_id`, `secret_access_key`, and optionally `session_token`, with Price List Query permissions. Pricing endpoint location is separate from the product region.
- Google Cloud: tenant service-account JSON with the Cloud Billing API enabled and appropriate access. Token exchange requests a read-only cloud scope.
- Huawei: tenant IAM token; each capture supplies the reviewed market/project/service/resource/specification/unit/usage dimensions through `huawei_spec`. Public capture uses the official website amount rather than a customer transaction price.

These APIs persist configuration and quote data inside the system. Deploying or running live exports still needs the tenant's own credentials and enabled integrations.

Protocol references: [Google Sheets value operations](https://developers.google.com/workspace/sheets/api/guides/values), [AWS GetProducts](https://docs.aws.amazon.com/boto3/latest/reference/services/pricing/client/get_products.html), [Google Cloud Billing authentication](https://docs.cloud.google.com/billing/docs/authentication).
