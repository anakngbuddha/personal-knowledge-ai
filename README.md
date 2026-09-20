# Personal Knowledge AI Workspace

> Write once. Understand everywhere.

An AI-grounded personal knowledge workspace: your own documents become one searchable,
conversational, **citable** knowledge base.

**Current state: V1 / Phase 1 complete (project setup + document ingestion).**
Upload a PDF, TXT, or DOCX and it becomes structured, embedded, full-text-indexed chunks
with page and section metadata intact. Retrieval, grounded generation, and evaluation are
next. See **[STATUS.md](STATUS.md)** for the exact done / not-done line.

---

## Stack

| Layer | Choice |
|---|---|
| Frontend | React + Vite (Vercel) |
| Backend | Python + FastAPI (Render) |
| Database | Aiven PostgreSQL + `pgvector` + full-text search |
| Embeddings | Google Gemini Embedding API (768 dims) |
| File storage | Cloudflare R2 |
| Cache / queue | none, deliberately |
| Dedicated vector DB | none, deliberately |

---

## What you need to fill in

Everything secret lives in env vars. Copy the template and fill it:

```bash
cp .env.example backend/.env
```

| Variable | Where to get it |
|---|---|
| `DATABASE_URL` | Aiven PostgreSQL service URI. Rewrite the scheme to `postgresql+psycopg://` and keep `?sslmode=require`. |
| `R2_ACCOUNT_ID`, `R2_ACCESS_KEY_ID`, `R2_SECRET_ACCESS_KEY`, `R2_BUCKET_NAME` | Cloudflare dashboard, R2 section: create a bucket and an API token. |
| `GEMINI_API_KEY` | Google AI Studio. |

Nothing else is required to run Phase 1.

Working without keys? Set `STORAGE_BACKEND=local` and `EMBEDDING_PROVIDER=fake` and the
whole pipeline runs end to end with deterministic stub vectors.

---

## Run it locally

```bash
# 1. Backend
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp ../.env.example .env      # then fill it in

# 2. Create the schema (enables pgvector, creates tables + HNSW/GIN indexes)
python ../scripts/init_db.py

# 3. Serve
uvicorn app.main:app --reload
```

```bash
# 4. Frontend
cd frontend
npm install
cp .env.example .env         # VITE_API_BASE_URL=http://localhost:8000
npm run dev
```

Open http://localhost:5173, upload a document, watch it go
`uploaded` to `processing` to `ready`, then click it to inspect the chunks and metadata.

### Verify your services are wired up

```bash
curl localhost:8000/health/dependencies
```

Returns a per-service pass/fail for PostgreSQL + pgvector, R2, and Gemini. This is the
Phase 0 exit check.

### Ingest a file without the UI

```bash
cd backend && python ../scripts/ingest_local.py ~/Downloads/lecture03.pdf
```

### Tests

```bash
cd backend && pip install -e ".[dev]" && pytest
```

---

## Repository layout

```text
backend/
  app/
    api/routes/     documents.py, health.py
    core/           config, logging, error types
    db/             SQLAlchemy models + session
    documents/      extraction, chunking, ingestion service
    embeddings/     base.py, gemini.py, fake.py, factory.py
    llm/            base.py  (Phase 3)
    retrieval/      (Phase 2)
    storage/        base.py, r2.py, local.py
  tests/
frontend/src/       components, hooks, services, types
scripts/            init_db.py, ingest_local.py, run_eval.py (Phase 4)
docs/               architecture.md, evaluation.md
```

---

## Deploy

- **Backend to Render (free tier)**: `render.yaml` is a Blueprint with `plan: free`
  (the default is paid Starter, which is why a free-only account cannot apply it).
  Use New → Blueprint and fill every `sync: false` secret. Schema is created on boot
  (`ENVIRONMENT=production`). Set `CORS_ORIGINS` to the exact Vercel origin.
- **Frontend to Vercel**: `vercel.json` is included. Root directory is `frontend`.
  Set `VITE_API_BASE_URL` to the Render URL (no trailing slash) and add the Vercel
  origin to `CORS_ORIGINS` on the backend.

Render's disk is ephemeral. Source files live in R2 only; that rule is enforced in code.

---

## Design rules this repo actually follows

1. Ship the smallest useful slice. Later phases stay unbuilt even when they look easy.
2. Citation metadata is captured during ingestion, never reconstructed afterwards.
3. One database until measurement says otherwise. No Redis, no Pinecone, no reranker.
4. Provider code sits behind interfaces so Gemini is swappable.
5. Retrieval quality gets measured against a labeled set, not vibes.
