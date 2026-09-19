# Phase 1 and Phase 2, as built

Implements `Project_Plan.md` **Phase 1 (Ingestion)** and **Phase 2 (Hybrid retrieval)**.

Read this before reading the code: it records what was changed against the plan and why,
and what is deliberately still missing.

---

## 1. The dependency the plan creates and this build had to resolve

Phase 1 requires sensitivity labels on every document. Phase 2 requires
*permission-aware retrieval*, and its exit criterion is "permission filtering has a
test that fails loudly if removed". Both depend on **Phase 0**, which is not built.

Two bad options and the one taken:

* Build Phases 1-2 with labels as decoration and no enforcement. Then Phase 2's exit
  criterion is unmeetable and every retrieval query gets rewritten later.
* Build all of Phase 0 first. That is not what was asked for.
* **Taken:** build the *minimum Phase 0 substrate these two phases structurally need* -
  the `organizations` table, `org_id` on every resource, sensitivity and approval
  labels, per-account grants, and a `Principal` that every retrieval call must carry.

**Not built, and not pretended to be:** authentication (email/password or OIDC),
session or JWT revocation, PostgreSQL row-level security, the append-only audit log,
the role-by-endpoint authorization matrix, CI secret scanning. `AUTH_MODE=owner_dev`
resolves every request to the single collateral owner from plan section 0, who
legitimately has full read access. `AUTH_MODE=dev_headers` exercises the restricted
path end to end. When Phase 0 lands, only `app/security/deps.py::resolve_principal`
changes; nothing in retrieval moves.

---

## 2. Phase 1: ingestion

| Plan item | Status | Where |
|---|---|---|
| Bulk upload, many files, folder drop | Done | `POST /documents` takes `files[]`, per-file result rows |
| URL ingestion | Done, SSRF-safe | `app/net/ssrf.py`, `POST /documents/url` |
| Pasted text | Done | `POST /documents/paste` |
| PDF, DOCX, **PPTX**, XLSX, TXT/Markdown, HTML | Done | `app/documents/extraction.py` |
| OCR for scanned PDFs | Behind a provider, off by default | `app/ocr/` - see §4 |
| Background processing, per-job status, retry with backoff, failed state | Done, durable | `app/jobs/`, `ingestion_jobs` table |
| Citation anchors: page, slide, sheet + cell range, heading path | Done | `app/documents/anchors.py` |
| Deduplication by content hash | Done | `content_hash` + partial unique index |
| Versioning on re-upload | Done | `version`, `supersedes_id`, `is_current` |
| Metadata at upload | Done, with a documented deviation | §3 |
| Content sniffing, not extension | Done | `app/documents/sniffing.py` |
| Malware scanning before parsing | Done, three backends | `app/documents/scanning.py` |
| Sandboxed parsing with timeouts | **Partial** | §4 |
| XXE and zip-bomb protection | Done | `app/documents/limits.py` |
| Prompt-injection containment | Done | `app/documents/injection.py` |

### Changes made on purpose

**The ingestion queue is a table, not `BackgroundTasks`.** The previous build queued
ingestion with FastAPI background tasks, which are lost when the process restarts. The
plan asks for per-job status and retry with backoff; an in-memory task list can provide
neither. `ingestion_jobs` is claimed with `FOR UPDATE SKIP LOCKED`. Still one worker,
no Redis, no Celery, exactly as the plan's scalability section specifies.

**The source file is never written to local disk.** Extraction works on bytes. The old
temp-file dance existed because the parsers were assumed to need paths; they do not, and
the safest handling of an untrusted file is to never persist it outside object storage.

**Chunking groups by the full anchor, not `(page, section)`.** The old key collapsed
every slide, sheet range and heading path into "no page, no section", which would have
put an entire deck into one chunk group the moment PPTX support landed.

**DOCX and PPTX tables are extracted.** They were silently dropped. Compatibility
matrices and pricing tiers live in tables, which is precisely the content the solution
composer will need in Phase 5.

**An explicit `chunk_overlap=0` is honoured.** `overlap = chunk_overlap or settings...`
turned 0 into 150, which would have quietly broken the zero-overlap arm of any chunking
experiment.

**Recorded schema migrations were added.** There were none: `create_all` adds missing
tables and leaves existing tables without their new columns, so an already-deployed
database would have diverged silently from the models. `app/db/migrations.py` applies
named, idempotent steps recorded in `schema_migrations`. This is not Alembic and should
become Alembic before a second deployment exists.

---

## 3. Deviation: metadata is not all mandatory at upload

The plan says seven metadata fields are "all required at upload". Implemented as
**safe defaults, never silent ones** instead. The argument, in full, is at the top of
`app/documents/metadata.py`. Short version:

* Phase 1's headline feature is a folder drop. Seven mandatory fields per file turns 50
  files into 350 inputs, and a single owner under deadline types `n/a` into all of them.
  Required fields filled with noise are worse than absent fields, because noise cannot
  be distinguished from data.
* The only property the safety controls actually need is that an *unset* field can never
  look permissive. So `sensitivity` defaults to `internal` and `approval_state` to
  `draft`, and an unknown label is **rejected**, never coerced to a default.
* Everything else defaults to explicit `unknown`/null, is listed in `metadata_missing`,
  and sets `metadata_complete = false`.
* The plan's real gate is preserved and made stricter: a document **cannot be promoted
  to `approved` while its metadata is incomplete**, which is what Phase 6's export check
  will hang off. `GET /documents?metadata_complete=false` is the chase list.
* A `resold` document additionally requires `source_of_truth_url`, because Phase 9's
  vendor-collateral monitoring has nothing to re-check without it.

Same end state, via a route that survives a folder drop.

---

## 4. Honest gaps

**"Parsing in a resource-limited sandbox"** is not implemented as a sandbox, because a
real one (seccomp, a separate container, cgroup memory limits) belongs to the deployment,
not to application code, and claiming one here would be a lie. What is implemented is
the part application code can enforce, and it is the part that stops the attacks named
in the plan: a wall-clock deadline checked in every extraction loop, hard caps on
archive entries, uncompressed size and compression ratio, rejection of any OOXML part
declaring a DTD or ENTITY, path-traversal rejection on member names, and a cap on total
extracted characters. Residual risk: a parser memory-exhaustion bug inside the limits.
Close it with container memory limits on the worker process.

**OCR is off by default.** `OCR_PROVIDER=tesseract` enables it and OCRs the embedded
images of pages with no text layer, which covers the usual one-image-per-page scan. Full
rasterisation (poppler / pdf2image) is the upgrade path. The default is `none` because
Tesseract is a native binary, the corpus is ~50 documents with one owner, and a scanned
PDF is better fixed at the source than silently OCR'd at 80% accuracy into collateral
that answers will later cite. A scanned PDF therefore **fails with a message saying
exactly that**, instead of succeeding with zero chunks.

**Malware scanning defaults to `heuristic`, which is not an antivirus.** It refuses
Office macros, PDF JavaScript and launch actions, embedded executables, and OOXML
packages with external relationship targets. `MALWARE_SCANNER=clamav` uses a real
scanner over clamd INSTREAM and **fails closed**: if it is configured and unreachable,
the upload is rejected. `none` is recorded on the document so a skipped scan is never
mistaken for a passed scan.

**Not built from Phase 1's test list:** the 500-document bulk drain is a script
(`scripts/bulk_load_test.py`) rather than a CI job, because it needs a database and 500
embedding calls. Run it with `EMBEDDING_PROVIDER=fake`.

---

## 5. Phase 2: hybrid retrieval

| Plan item | Status |
|---|---|
| pgvector + tsvector with RRF, deterministic | Done. `app/retrieval/fusion.py` is pure and unit-tested |
| Filtered retrieval, **required not optional** | Done: product, vendor, ownership, account, approval state, sensitivity, freshness, document type, document id |
| Filters apply **before** fusion | Structural: both branches read the same `candidates` CTE |
| Permission-aware retrieval | Done. Enforced, not advisory |
| `POST /search` debug endpoint with scores and fusion inputs | Done, always on |
| Labeled set of 50+ questions | **Template only** - see below |
| Baseline recorded in writing before tuning | Harness done: `scripts/run_eval.py --out docs/retrieval-baseline.md` |
| Latency budget p95 < 500 ms | Measured and returned per query in `timings_ms` |

### How "filters before fusion" is guaranteed

`candidates` is one CTE: chunks joined to documents, filtered by permission predicates,
corpus predicates (current version, `status = ready`) and caller filters. The vector
branch and the keyword branch both `JOIN candidates`. There is no path from an
unfiltered chunk into either rank list. `tests/test_search_sql.py` asserts this against
the compiled SQL.

### How the permission filter fails loudly if removed

* `app/retrieval/permissions.py::predicates_for` is the only producer of permission
  predicates and always produces at least tenant isolation plus a sensitivity ceiling.
* `assert_enforced` raises `PermissionFilterMissing` if a predicate set reaches the query
  builder with no `Origin.PERMISSION` entry. `POST /search` turns that into a 500 and
  never degrades to an unfiltered search.
* `tests/test_permissions.py` is the regression suite; `tests/test_integration.py`
  contains the end-to-end leak test, which also asserts the restricted chunk is absent
  from `candidate_count`, not merely filtered out of the response.

A caller's filter can never widen their grant: permission and filter predicates are
ANDed identically, so asking for `customer_data` while capped at `internal` returns
nothing rather than leaking.

`vendor_restricted` is deliberately **not** on the sensitivity ladder. It is
contractual, not hierarchical, and putting it on the ladder would make a customer-data
grant silently imply a partner-NDA grant.

### What is not done, and should not be faked

**The labeled question set is a template.** `docs/eval/questions.json` ships six
question *shapes* that matter (capability lookup, prerequisites, support path, pricing
with a sheet anchor, an exact-phrase compatibility question where vector-only retrieval
tends to lose, and an account-scoped question that must be invisible without a grant).
Writing 50 plausible-looking questions against collateral that does not exist would
produce a baseline that measures nothing. The harness, the metrics (hit@1, hit@5, MRR,
p50/p95) and the three-way A/B/C comparison are all implemented and run as soon as real
collateral and real questions exist.

**`docs/retrieval-baseline.md` is intentionally absent** until `run_eval.py` produces
it. The plan's standing rule is to record the baseline *before* tuning; a hand-written
baseline would defeat the point.

### Known performance trade-off

Filtering before the vector search means the HNSW index cannot be used as a pure
approximate-nearest-neighbour scan; PostgreSQL will filter then sort. At ~50 documents
this is irrelevant and correctness wins. `timings_ms` is returned on every query as the
tripwire, per the plan's "add infrastructure only when a measurement demands it".

---

## 6. Running it

```bash
cd backend
pip install -r requirements.txt
python ../scripts/init_db.py            # extensions, tables, recorded migrations
uvicorn app.main:app --reload           # worker runs in-process by default

# offline, no keys needed:
EMBEDDING_PROVIDER=fake STORAGE_BACKEND=local uvicorn app.main:app --reload

# separate worker instead:
WORKER_ENABLED=false uvicorn app.main:app     # and, elsewhere:
python ../scripts/worker.py

python -m pytest tests -v                      # integration tests skip without DATABASE_URL
DATABASE_URL=postgresql+psycopg://... python -m pytest tests -v   # full suite
```

Baseline:

```bash
cd backend
python ../scripts/seed_eval_set.py ../docs/eval/questions.json
python ../scripts/run_eval.py --out ../docs/retrieval-baseline.md
```

---

## 7. What Phase 3 inherits

* `app/documents/injection.py::wrap_untrusted` - **every** source passed to a model must
  go through it, and `SYSTEM_CONTRACT` must be in the system prompt.
* `SearchHit` already carries the citation anchor, freshness, approval state, vendor and
  sensitivity of every source, which is what Phase 3 has to show next to each answer.
* `search(mode=...)` keeps the baseline comparison on one code path.
