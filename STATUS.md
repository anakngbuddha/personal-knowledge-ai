# Build Status

Roadmap source: *Personal Knowledge AI Workspace - Product Plan & Roadmap*.
Last updated: 2026-09-18. Scope of this commit: **Phase 0 + Phase 1 of V1**.

---

## Phase 0 - Project setup

| Task | State | Notes |
|---|---|---|
| Create repository | Done | This repo. |
| Create React app | Done | Vite + React + TypeScript in `frontend/`. |
| Create FastAPI app | Done | `backend/app/main.py`, health + documents routers. |
| Connect PostgreSQL (local or Aiven) | Code done, needs your `DATABASE_URL` | SQLAlchemy 2.0 + psycopg 3. |
| Enable pgvector | Code done | `scripts/init_db.py` runs `CREATE EXTENSION IF NOT EXISTS vector`. |
| Configure environment variables | Done | `.env.example` + `app/core/config.py`. |
| Deploy frontend to Vercel | Config done, deploy is yours | `vercel.json`. |
| Deploy backend to Render | Config done, deploy is yours | `render.yaml`, all secrets `sync: false`. |
| Create R2 bucket | Yours | Then fill the four `R2_*` vars. |
| Verify Gemini API connectivity | Tooling done | `GET /health/dependencies` checks all three services. |

**Exit criteria:** met in code. Flips to verified once your keys are in and
`/health/dependencies` returns `ok: true`.

---

## Phase 1 - Document ingestion

| Task | State | Where |
|---|---|---|
| Upload file | Done | `POST /documents`, 25 MB cap, PDF/TXT/DOCX only. |
| Save source file to R2 | Done | `app/storage/r2.py`, keyed `workspaces/{ws}/documents/{doc}/{name}`. |
| Create document row | Done | `app/db/models.py::Document`. |
| Extract text | Done | pypdf / python-docx / decoded text, `app/documents/extraction.py`. |
| Preserve page + section metadata | Done | Per-page blocks for PDF, heading-styled sections for DOCX, `#` headings for TXT. Document metadata (title/author) stored as `jsonb`. |
| Deterministic chunking | Done | `app/documents/chunking.py`. Chunks never cross a page or section boundary; splits prefer paragraph, then line, then sentence; fixed overlap; character offsets recorded. |
| Generate embeddings | Done | `app/embeddings/gemini.py`, batched, 768 dims, cosine-normalized, 429-aware with exponential backoff. |
| Save chunks and vectors | Done | Batched commits so a long document reports progress and never holds everything in memory. |
| Populate full-text search data | Done | `search_vector` is a PostgreSQL **generated** column + GIN index, so it can never drift from the text. |

**Exit criteria:** met. Documents reach `ready`, and chunk metadata is inspectable via
`GET /documents/{id}/chunks` or the UI's chunk panel.

### Also included (small, load-bearing extras)

- `failed` status with a stored `error_message`, plus a `POST /documents/{id}/process` retry.
- Delete removes the R2 object and cascades chunk rows.
- Temp files always cleaned up in a `finally`; nothing persistent touches Render's disk.
- `EMBEDDING_PROVIDER=fake` + `STORAGE_BACKEND=local` run the whole pipeline with no keys.
- Tests for chunk determinism, page/section isolation, offset monotonicity, extraction.
- `scripts/ingest_local.py` to exercise the pipeline without the UI.
- Empty tables already created for later phases: `conversations`, `messages`,
  `evaluation_questions`.

---

## What is left

### Yours (config, not code)

- [ ] Aiven PostgreSQL service, then `DATABASE_URL` (use `postgresql+psycopg://`)
- [ ] Cloudflare R2 bucket + API token, then `R2_*`
- [ ] Google AI Studio key, then `GEMINI_API_KEY`
- [ ] Run `python ../scripts/init_db.py` once
- [ ] Deploy: Render (backend) + Vercel (frontend), then set `CORS_ORIGINS`

### Phase 2 - Retrieval (not started)

- [ ] Query embedding path
- [ ] pgvector similarity query
- [ ] PostgreSQL FTS query
- [ ] Reciprocal Rank Fusion, fixed `RRF_K`, deterministic
- [ ] Top-K selection using `TOP_K`
- [ ] `POST /search` debug endpoint returning retrieved chunks
- **Exit:** retrieval is measurable without touching the LLM.

### Phase 3 - Grounded generation (not started)

- [ ] Gemini generation provider behind `app/llm/base.py`
- [ ] Grounded system prompt that refuses to answer beyond the context
- [ ] Context formatting with citation metadata
- [ ] Citation extraction into `messages.citations` (column already exists)
- [ ] `POST /conversations`, `GET /conversations`, `GET /conversations/{id}`, `POST /conversations/{id}/messages`
- **Exit:** a question returns an answer with a source citation.

### Phase 4 - Evaluation (not started)

- [ ] 20-30 labeled questions seeded via `scripts/seed_eval_set.py`
- [ ] Automated retrieval evaluation in `scripts/run_eval.py`
- [ ] Compare vector-only vs keyword-only vs hybrid+RRF
- [ ] Record retrieval hit rate + citation accuracy as a written baseline
- **Exit:** V1 meets a target chosen *after* the first measurement.

### Phase 5 - UI refinement (partially standing)

- [x] Document list with upload / processing / ready / failed states
- [x] Upload progress and error banner
- [x] Mobile-friendly single-column fallback
- [ ] Chat history view
- [ ] Citation display (clickable source)
- **Exit:** someone else can use it without instructions.

---

## Still deliberately not built

Notes editor, folders and tags, backlinks, knowledge graph, AI relationships, reranker,
multi-user accounts, collaboration, multimodal ingestion, OCR, Redis, Pinecone.

Nothing here gets pulled forward because it looked easy. Phase 2 is next.

---

## Known deviations from the plan document

1. `GEMINI_EMBEDDING_MODEL` defaults to `gemini-embedding-001`, not the plan's placeholder
   `gemini-embedding-2`, which is not a real model ID. Still fully configurable.
2. Chunks are hard-bounded by page and section rather than by character windows alone. This
   trades a little chunk-size uniformity for citation precision, which V1 cares about more.
3. A `fake` embedding provider was added so ingestion is testable with no key and no
   network. That is the provider abstraction earning its keep on day one.
