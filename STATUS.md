# Build Status

Plan of record: **`Project_Plan.md`** (rev 2, 2026-09-19). It renumbers the phases, so the
old numbering in this file's history does not line up; `docs/ROADMAP.md` is superseded
where the two conflict.

Last build scope: **Phase 1 (Ingestion) + Phase 2 (Hybrid retrieval)**.
Full write-up, including every deviation and every remaining gap: **`docs/PHASE1-2.md`**.

---

## Phase status against Project_Plan.md

| Phase | Name | State |
|---|---|---|
| 0 | Foundation and security baseline | **Partial.** Data model + enforcement seam only. No authN, no RLS, no audit log |
| 1 | Ingestion | **Done**, with the metadata deviation argued in `docs/PHASE1-2.md` §3 |
| 2 | Hybrid retrieval | **Done**, except the labeled question set is a template and the baseline has not been run |
| 3 | Grounded answers | Not started |
| 4 | Product catalog and typed graph | Not started |
| 5 | Solution composer | Not started |
| 6-10 | Workflows, freshness, hardening | Not started |

---

## What is left before Phase 3 starts

### Yours (config, not code)

- [ ] Aiven PostgreSQL, then `DATABASE_URL` (use `postgresql+psycopg://`)
- [ ] Cloudflare R2 bucket + token, then the four `R2_*` vars
- [ ] Google AI Studio key, then `GEMINI_API_KEY`
- [ ] `cd backend && python ../scripts/init_db.py`
- [ ] Deploy: Render (backend) + Vercel (frontend), then `CORS_ORIGINS`

### Phase 2's unfinished business

- [ ] Write the 50+ real SE questions into `docs/eval/questions.json` (six shapes are
      templated; the current file is deliberately not a usable labeled set)
- [ ] `python ../scripts/seed_eval_set.py ../docs/eval/questions.json`
- [ ] `python ../scripts/run_eval.py --out ../docs/retrieval-baseline.md` - **this is the
      written baseline Phase 2 requires before any tuning**
- [ ] Run `scripts/bulk_load_test.py --count 500` with `EMBEDDING_PROVIDER=fake` and record
      the numbers

### Phase 0, whenever it is scheduled

Authentication (password or OIDC) with revocation, PostgreSQL row-level security, the
append-only audit log, the role-by-endpoint authorization matrix, CI with a coverage
floor, dependency and secret scanning. Only `app/security/deps.py::resolve_principal`
has to change; retrieval is already permission-aware.

---

## Endpoints

| Method | Path | Purpose |
|---|---|---|
| GET | `/health`, `/health/dependencies` | Liveness, and whether the safety controls are actually on |
| POST | `/documents` | Bulk upload (`files[]`), per-file result rows |
| POST | `/documents/url` | URL ingestion through the SSRF-safe fetcher |
| POST | `/documents/paste` | Pasted discovery notes / RFP extracts |
| GET | `/documents` | List, filterable by status and `metadata_complete` |
| GET/PATCH/DELETE | `/documents/{id}` | Read, curate metadata, delete |
| POST | `/documents/{id}/approval` | Promotion gate: incomplete metadata cannot be approved |
| POST | `/documents/{id}/process` | Requeue ingestion |
| GET | `/documents/{id}/status` | Document status + its latest job |
| GET | `/documents/{id}/chunks` | Chunks with their citation anchors |
| **POST** | **`/search`** | Hybrid retrieval, with predicates, branch ranks and timings exposed |
| GET | `/jobs`, `/jobs/stats` | Per-job status; every failure explainable and retryable |

---

## Known deviations from the plan document

1. **Metadata is not all mandatory at upload.** Safe defaults plus a
   `metadata_complete` flag and an approval gate instead. Argued in
   `docs/PHASE1-2.md` §3 and in `app/documents/metadata.py`.
2. **Parsing is limit-enforced, not sandboxed.** A real sandbox is a deployment concern.
   What application code can enforce is enforced; the residual gap is named in
   `docs/PHASE1-2.md` §4 rather than papered over.
3. **OCR is off by default.** A scanned PDF fails with an actionable message instead of
   being silently OCR'd into citable collateral.
4. **The ingestion queue is a PostgreSQL table**, not `BackgroundTasks`, because per-job
   status and retry with backoff are impossible with an in-memory task list.
5. **`vendor_restricted` is not on the sensitivity ladder.** It is contractual, not
   hierarchical.
6. **`GEMINI_EMBEDDING_MODEL` defaults to `gemini-embedding-001`**, not the plan's
   placeholder `gemini-embedding-2`, which is not a real model ID.
7. **Chunks are bounded by citation anchor**, trading chunk-size uniformity for citation
   precision.
