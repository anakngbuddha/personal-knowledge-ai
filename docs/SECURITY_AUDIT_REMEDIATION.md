# Security audit remediation and validation

Audit source: the user-supplied pasted audit, covering 60 numbered findings plus the unnumbered legacy `/auth/token` finding. Remediation date: 2026-10-01. This report describes the working-tree changes; it is not a deployment attestation.

**Status:** most application findings have code fixes and local regression coverage. Production PostgreSQL enforcement, identity-provider interoperability, OS/network isolation, retention rollout, and large-dataset performance still require the evidence listed below. Do not mark the entire audit closed from the local verifier alone.

## Validation evidence

- `python scripts/verify_project.py`: Python compilation, backend tests, frontend tests/build/typecheck, and Graphify integrity. Local result: 310 Python files compiled; 715 backend tests passed, 38 PostgreSQL tests skipped; 30 frontend tests passed and the frontend build/typecheck passed. PostgreSQL-only skips are explicitly reported; they are forbidden in CI through `REQUIRE_DB_TESTS=1` and a JUnit skip gate.
- Frontend: 30 tests across 10 files, including hostile API-origin overrides, session persistence, unsafe paths/redirects, Markdown HTML/script/link sanitization, and citation buttons. `npm run build` includes `tsc -b`.
- `npm audit --json`: zero known vulnerabilities after updating Vite/Vitest and the React plugin.
- `pip-audit -r backend/requirements.lock --disable-pip --no-deps`: zero known vulnerabilities in the pinned runtime requirements when checked during remediation. The deployment lock targets Linux/Python 3.12; local tests ran on Windows/Python 3.14. The exact Linux environment must also pass CI.
- Gitleaks v8.30.0, pinned to commit `6eaad039603a4de39fddd1cf5f727391efe9974e`: 132 Git commits, approximately 31 MB, scanned with `--redact --log-opts=--all`; no leaks found. The tracked working-tree diff also passed a redacted scan. A clean scan is not proof that every possible secret format is detected.
- Deployment JSON/YAML parsed successfully, documentation links checked, and `git diff --check` passed. GitHub Actions and the deployed Render/Aiven/Vercel services were not run from this workspace.

## Finding inventory

“Implemented” means a repository fix exists. “Gate” requires external validation or configuration before production closure. The deployment gates are separate from local regression results.

| Finding | Status | Change / remaining evidence |
| --- | --- | --- |
| Legacy token endpoint (unnumbered) | Implemented | `/auth/token` always returns 410; callers cannot select a role and mint a token. |
| AUTH-04 | Implemented + gate | OIDC Code + PKCE S256; server-stored, browser-bound, expiring, atomic single-use state; mandatory nonce; discovery/JWKS signature verification. Legacy implicit callback returns 410. Test a real provider in staging. |
| AUTH-05 | Implemented + gate | OneLogin strict SAML XML Signature validation, configured X509 trust, signed response/assertion requirements, audience/ACS/request-ID/time checks, and single-use browser-bound state. Legacy HMAC assertion parsing is disabled. Test the deployed certificate and real IdP response. |
| AUTH-06 | Implemented | SSE query-string bearer tokens are rejected; Authorization headers are required. |
| AUTH-07 | Implemented | Document/catalog mutations require solutions engineer or above; approval requires admin. Approval cannot be bypassed through create/patch metadata. Writer draft curation retains tenant/sensitivity filters. |
| AUTH-08 | Implemented + gate | Explicit owner comparison fixes admin-as-owner escalation; peer/higher assignment and editing are rejected; organization-row locks serialize last-owner checks; role changes are audited. Exercise competing requests on PostgreSQL. |
| AUTH-09 | Implemented | Stable public scanner/storage/provider/operational/MCP errors; exception details remain in redacted operational logs. |
| AUTH-10 | Implemented + gate | API and Vercel security headers, request IDs, production HSTS, bounded request bodies, restricted CORS methods/headers. Ordinary authentication uses explicit bearer headers; SSO uses temporary HttpOnly binding cookies and state validation. Verify deployed headers and origins. |
| AUTH-11 | Implemented | MCP transport requires `typ=mcp` and explicit `mcp:read`; web JWTs and missing/malformed scopes fail. |
| AUTH-12 | Implemented | Collateral reads include tenant/workspace and document authorization predicates; stored string IDs are normalized safely. |
| AUTH-13 | Implemented | Numeric finite required expiry/issued-at, expiry boundary, future `iat`/`nbf` rejection, and bounded lifetimes. |
| AUTH-14 | Implemented | Bounded list parameters across members/catalog/map/review/documents; messages and source inspection use SQL pagination. Review/backlink totals are real counts. |
| AUTH-15 | Implemented | Notes graph resolves targets from tenant/workspace-scoped bounded maps; account labels honor caller account grants. |
| AUTH-16 | Implemented | Explicit graph node/edge caps and bounded backlinks; no per-link target lookup loop. Graph responses are bounded views of the graph. |
| AUTH-17 | Implemented | Environment-enabled integrations no longer implicitly grant access across organizations; organization configuration is required. |
| AUTH-18 | Implemented | Immutable Sheets export lookup includes the principal's organization. |
| AUTH-19 | Implemented | SSO operational status requires admin access. |
| AUTH-20 | Implemented | Durable audit details redact sensitive keys, nested values, tokens and URLs, with depth/count/string/byte caps. |
| AUTH-21 | Implemented | Valid Fernet material is mandatory; versioned envelopes and a previous-key ring support staged rotation. |
| AUTH-22 | Implemented | Final formatted log messages/tracebacks redact bearer/JWT/key-value secrets, connection credentials, emails, private keys and URLs; upload rejection logs omit filenames. Request failures carry request IDs. |
| AUTH-23 | Implemented | MCP tools/list filters write tools by caller permission. |
| AUTH-24 | Implemented | MCP HTTP transport permits only the fixed approved provider URLs and Authorization header; redirects and CR/LF headers are rejected. |
| DB-01 | Implemented + gate | Ordinary tenant policy has no `org_id IS NULL` sharing branch. Existing NULL rows remain quarantined until an explicit migration assigns ownership. |
| DB-02 | Implemented + gate | Forced RLS covers messages, join tables, and memberships. Login's pre-tenant membership lookup is scoped to a verified password identity and restores previous session scope in `finally`; bearer/SSO membership lookups scope first. Evaluation questions are explicitly system-only offline data. |
| DB-03 | Gate | Required RLS rejects non-PostgreSQL, superuser/BYPASSRLS, missing FORCE, and unexpected policies. CI prepares and checks an actual restricted runtime connection. Obtain equivalent evidence from the deployed role. |
| DB-04 | Implemented | History uses descending SQL LIMIT before reversing the selected messages; timestamps and ID ordering are stable. |
| DB-05 | Implemented | Bounded graph/catalog/notebook views, outer-joined notebook membership and batched graph review relationships reduce unbounded reads/N+1 work. Production query-count/load measurements remain a gate. |
| DB-06 | Implemented + gate | Validated timestamp/UUID cursor pagination covers documents, notes, conversations and messages; source/chat navigation uses cursors. Legacy API offsets are capped at 10,000. Validate index plans and latency on large tenant datasets. |
| DB-07 | Implemented + gate | Tenant/timestamp, conversation-message, queue-claim, edge-status, audit-log and product trigram indexes are included in migrations. Validate plans on production-shaped data and use a controlled migration window; migrations use ordinary CREATE INDEX, not concurrent production index creation. |
| DB-08 | Implemented | Catalog create/update validates collateral IDs against the tenant and workspace before persistence. |
| DB-09 | Implemented + gate | Hardened migrations recreate policies; boot posture checks policy presence/expressions and unexpected extra policies, rather than trusting a policy name alone. Run policy-tampering tests on PostgreSQL. |
| DB-10 | Implemented + policy gate | Administrator-defined tenant policies default to disabled. Bounded previews/purges honor legal holds and references; committed object-deletion outboxes retry cleanup. Orphan inventory is read-only; commercial/audit evidence is excluded. Provider backup/lifecycle configuration and approved rollout remain deployment gates. |
| DB-11 | Implemented + gate | PostgreSQL triggers validate tenant/workspace relationships for tenant-bearing foreign keys; tenant reassignment is rejected, including system writes. RLS checks derived join-table parent ownership. Run migration and malformed-parent tests on PostgreSQL. |
| APP-01 | Implemented | Document service enforces maximum bytes before scanning/storage. |
| APP-02 | Implemented | RFP CSV/XLSX byte, row, column and cell caps; OOXML archive/XXE/zip-bomb preflight. |
| APP-03 | Implemented | Workers verify job/document/workspace organization consistency before privileged processing; processing repeats the expected-organization check. |
| APP-04 | Implemented | Local storage resolves paths and rejects escapes/absolute keys before filesystem mutations. |
| APP-05 | Implemented | Allowlisted tool arguments receive JSON Schema validation, unknown-field rejection and a byte cap; nonfinite/invalid JSON values fail closed. |
| APP-06 | Mitigated + gate | Production browser tools are disabled pending an isolated egress service. Preflight URL validation in development is not a connection-level network boundary. |
| APP-07 | Implemented | Exact normalized media-type allowlist matching replaces prefix acceptance. |
| APP-08 | Implemented + gate | Production document extraction runs in a killable spawned process, with Linux CPU/address-space caps and bounded IPC output. Positive extraction and hard-deadline cleanup are tested locally. The parser still needs deployment filesystem/network containment; RFP spreadsheet parsing remains bounded in-process. |
| APP-09 | Implemented | ClamAV replies have a fixed accumulation cap. |
| APP-10 | Implemented + gate | Per-file and aggregate request/batch limits; per-tenant 100 uploads/minute and 500 pending-document caps with shared database row serialization. Confirm quota concurrency/fairness on PostgreSQL under load. |
| APP-11 | Implemented | GraphRAG requires and filters organization scope, validates workspace ownership and caps expansions. |
| APP-12 | Implemented | Same strict/versioned credential encryption as AUTH-21. |
| APP-13 | Implemented + containment gate | Actual SDK calls execute in spawned processes with hard deadlines, bounded IPC output and two-call admission. Timed-out workers and descendant processes are killed and reaped; resistant-worker tests pass. Production stdio also requires a separately verified OS wrapper for filesystem/network containment. |
| APP-14 | Implemented | Studio document-derived summaries/facts use explicit untrusted-content fences. |
| INF-01 | Implemented + gate | Vercel CSP, HSTS, nosniff, frame/referrer/permissions headers. Align `connect-src` with the exact deployed API origin and smoke-test in a browser. |
| INF-02 | Implemented + gate | Read-only workflow permissions, immutable action pins, no persisted checkout credentials, hashed Python installs, npm ci, complete DB/frontend/security gates, dependency scans and a pinned history secret scan. Execute the workflow on the reviewed commit. |
| INF-03 | Implemented | Repository-managed automatic script hooks are disabled. Graph updates continue explicitly under AGENTS.md. Re-enable hooks only after reviewing scripts and the trust boundary. |
| INF-04 | Implemented | 140 tracked log/build/test-storage artifacts were removed from the Git index; local copies are preserved. Ignore rules prevent recommitting them. Existing history was scanned, not rewritten. |
| INF-05 | Implemented + gate | Production defaults and validation reject automatic approval, private URL fetching, weak authentication, unsigned SAML and insecure scanner selection. Configure an available ClamAV service; unreachable scanning fails closed. Crawls always honor robots.txt. |
| INF-06 | Gate | Release evidence checklist below is mandatory; local success is not enterprise readiness certification. |
| FE-01 | Implemented | API origin comes from trusted build configuration or local development defaults; query/local-storage overrides cannot redirect bearer tokens. Absolute/alternate-origin paths and HTTP redirects are rejected. |
| FE-02 | Implemented | Persistent JWT restoration/localStorage writes are removed and legacy stored sessions are cleared. Tab-scoped session storage remains; XSS prevention is still essential. |
| FE-03 | Implemented | Source pages, older conversation pages and earlier-message loading are accessible through bounded requests, rather than silently stopping at the first response. |
| FE-04 | Implemented | Privileged connector panel requires admin/owner; backend RBAC remains the enforcement boundary. |
| DEP-01 | Implemented + gate | Hash-pinned runtime/dev locks, deployment require-hashes, pip-audit and Dependabot. Verify the exact Linux/Python 3.12 installation in CI. |
| DEP-02 | Implemented | Exact upgraded toolchain versions, updated lock, npm ci in deploy/CI, lock-drift check and npm audit. |
| TST-01 | Implemented + gate | CI includes frontend security tests/build and a real PostgreSQL service; unreachable database or any skipped CI test fails the workflow. No local PostgreSQL service was available. |
| TST-02 | Implemented | Direct regression cases for origin/token persistence/Markdown safety/citation controls, plus backend attack-input, RBAC, state, crypto, quota and parser tests. |

## Retention classes and safe rollout (DB-10)

Retention periods require the organization's approved business/privacy policy. The following classes define the scope; no period in this report authorizes deletion.

| Class | Data | Required disposition |
| --- | --- | --- |
| Ephemeral authentication | SSO state, browser binding, PKCE verifier | Five-minute expiry and atomic consumption are implemented; expired transactions are cleaned on new starts. |
| Customer content | Document versions, chunks, notes, messages, generated artifacts | Administrator-configured document, note and conversation expiry; legal holds and provenance references take precedence. Purges are explicit and bounded. Generated commercial evidence is excluded. |
| Operational execution | Terminal ingestion/workflow jobs and error payloads | Approved short retention after terminal state; never purge pending/running jobs or active leases. |
| Commercial and audit evidence | Price observations, issued quotes/versions/exports, sales claims, audit logs | Explicit evidence-retention schedule and legal holds. No generic age-based DELETE. |
| Objects and backups | R2/local objects, backup snapshots | Reconcile with live DB references; delayed, idempotent object-deletion outbox after DB success; provider lifecycle and backup expiry must match policy. |

The user selected administrator-defined policy with deletion disabled by default. `GET /ops/retention/policy` returns that default; `PUT /ops/retention/policy` accepts approved periods in days and explicit enablement. Only administrators/owners can configure or execute these operations. Supported classes are document, note, conversation, terminal ingestion job and terminal task execution. Audit logs and commercial evidence cannot be selected.

`POST /ops/retention/holds` protects individual resources; the policy can also place the tenant under a legal hold. `POST /ops/retention/purge` defaults to `dry_run=true`, with a combined batch limit of 500. Preview candidates can still be retained during application because of provenance or foreign-key references. Database changes and object-deletion outbox entries commit together; `POST /ops/retention/object-cleanup` requires explicit `dry_run=false` and an enabled, unheld policy before retryable byte deletion. `GET /ops/retention/orphans` inventories old, unreferenced objects in an authorized workspace and never deletes them. Local object inventory is best-effort under concurrent filesystem changes. No scheduler enables deletion automatically.

Disposable regression fixtures verify disabled defaults, tenant isolation, legal holds, reference-preserving savepoint rollback, committed outbox cleanup and retry, forbidden evidence classes and read-only orphan inventory. PostgreSQL concurrency, provider lifecycle/backup expiry and restore evidence still require staging validation. No existing application data was purged.

## Deployment and closure gates

1. Run all tests with a disposable PostgreSQL/pgvector service and `REQUIRE_DB_TESTS=1`; there must be zero skips. Exercise the tenant-parent triggers, membership login scope restoration, NULL-row quarantine, policy tampering, concurrent ownership changes and upload quotas.
2. Apply migrations `0037`–`0044` with the migration role, review pre-existing tenant/workspace inconsistencies first, and grant runtime access separately. NULL tenant backfills must happen before immutable tenant guards; normal application writes cannot reassign ownership. Run `scripts/check_ci_rls.py` against the actual restricted staging role and retain its result.
3. Run the full CI workflow on the exact patch commit and exact Linux/Python 3.12 lock. The local Python version differs. Preserve sanitized reports as CI artifacts, rather than committing raw operational logs.
4. Configure genuine Fernet keys. Weak normalized legacy key material is deliberately rejected: securely migrate old ciphertext before removing old keys, retain previous valid keys only during rotation, and never copy secret values into Git or this report.
5. Provision ClamAV and confirm scanner outages reject ingestion. Validate extraction Linux resource caps; isolate parser filesystem/network access. Configure and test the MCP OS wrapper before enabling production stdio integrations. Production browser tools stay disabled until an egress boundary is implemented.
6. Configure the supported OIDC environment issuer/client/redirect and SAML X509/HTTPS endpoint/ACS/entity. Provision active local memberships; OIDC verified email maps to an existing account and local role. SAML currently needs a NameID matching the provisioned subject identity. These hardened flows use the environment provider/default tenant; legacy per-organization HMAC provider records do not configure the new standards path. Complete real-provider, replay, wrong-audience, expired-assertion and cross-site cookie tests before enabling SSO.
7. Match Vercel CSP `connect-src`, `VITE_API_BASE_URL` and backend CORS to the exact deployment; validate headers on successful and error responses and verify auth across refresh/new tabs and SSO redirects. Bearer tokens are not persisted across new tabs.
8. Validate cursor plans, retention/outbox concurrency and OS containment in staging. Approve each tenant retention policy and align provider lifecycle/backup expiry before enabling deletion. Capture large-tenant EXPLAIN/query-count/latency, load/fairness/SLO, live-provider quality, retry/idempotency, restore and audit evidence before declaring enterprise readiness.

No production deployment, schema migration, account notification, secret rotation, Git history rewrite or application-data purge was executed during this remediation.
