---
name: security-and-scalability
description: >-
  Use this skill to audit, harden, and optimize the Personal Knowledge AI application for enterprise security,
  OWASP compliance, input sanitization, high-concurrency scalability, vector indexing, and memory efficiency.
---

# Security and Scalability Engineering Skill

This skill provides architectural patterns, auditing workflows, and implementation checklists to ensure the Personal Knowledge AI application is inherently secure, resilient against vulnerabilities, and capable of scaling to high document volumes and concurrent users.

## 1. Security Engineering & Auditing

### A. Authentication & Authorization
- **JWT & Token Validation**: Enforce standard expiration (`exp`), issuer (`iss`), and cryptographic signature checking on all user and bearer tokens.
- **RBAC & Data Segregation**: Every query against documents, chunks, or user workspaces must include ownership filters (e.g. `workspace_id = current_user.workspace_id`). Prevent Insecure Direct Object Reference (IDOR).
- **Password & Secret Storage**: Never store plaintext credentials. Use Argon2id or Bcrypt for password hashes.

### B. Input Validation & Injection Defense
- **Pydantic Strict Schemas**: Validate request payloads strictly. Reject unrecognized fields and enforce type constraints (e.g., max string lengths, valid UUIDs, regex patterns).
- **SQL & Vector Injection Prevention**:
  - Always use parameterized queries or SQLAlchemy ORM (`select(...)`).
  - Never concatenate user strings into raw SQL or Cypher statements.
  - Sanitize similarity search filter criteria against an allowlist of metadata columns.

### C. Secrets & Environment Isolation
- All secrets (database URLs, AWS S3 keys, LLM API tokens, JWT secret keys) must be loaded from `.env` via `app.core.config.Settings`.
- Never commit `.env` or sensitive credentials to git.
- Audit dependencies for vulnerabilities:
  ```bash
  pip-audit
  # or
  npm audit --prefix frontend
  ```

### D. Network, Headers & Rate Limiting
- Enforce CORS origins strictly (avoid wildcard `*` with credentials).
- Apply security headers: Content-Security-Policy (CSP), X-Frame-Options (DENY), X-Content-Type-Options (nosniff).
- Implement rate limiting (e.g. SlowAPI or Redis token bucket) on document upload, OCR/extraction, and LLM query endpoints to mitigate DoS and token exhaustion attacks.

---

## 2. Scalability & High-Performance Engineering

### A. High-Scale Vector Search (`pgvector`)
- **Indexing Strategy**: Plain vector tables default to sequential scan. As documents scale past 1,000s of chunks, queries become slow. Ensure appropriate index creation:
  - **HNSW (Hierarchical Navigable Small World)**:
    ```sql
    CREATE INDEX ON document_chunks USING hnsw (embedding vector_cosine_ops)
    WITH (m = 16, ef_construction = 64);
    ```
    Provides superior recall and query latency under high read volume.
  - **IVFFlat**: Suitable when memory is constrained. Remember to build after data is populated:
    ```sql
    CREATE INDEX ON document_chunks USING ivfflat (embedding vector_cosine_ops)
    WITH (lists = 100);
    ```
- Always set query search radius / ef_search: `SET hnsw.ef_search = 40;`.

### B. Database Connection Pooling
- Configure SQLAlchemy async / sync engine pooling:
  ```python
  engine = create_engine(
      settings.DATABASE_URL,
      pool_size=20,
      max_overflow=10,
      pool_timeout=30,
      pool_recycle=1800,
      pool_pre_ping=True,
  )
  ```
  `pool_pre_ping=True` prevents stale connection errors after DB idle timeouts.

### C. Asynchronous & Queue-Backed Processing
- Heavy processing (document ingestion, PDF parsing with `pypdf`/`python-docx`, text chunking, and embedding API calls) must never block HTTP request threads.
- Utilize FastAPI `BackgroundTasks` or message queues (Celery, Arq, Redis Streams) for ingestion jobs.
- Return a job ID / task status endpoint (`GET /api/v1/jobs/{id}`) so clients can poll or receive websocket updates.

### D. Memory Management & Streaming
- **Lazy Chunking**: Use Python generators (`yield`) during document reading to stream chunks rather than loading 100MB documents completely into RAM.
- **Streaming Responses**: For LLM generation responses, use FastAPI `StreamingResponse` with server-sent events (SSE) to reduce time-to-first-token and keep worker memory low.
- **Pagination**: Strictly enforce cursor or offset/limit pagination on all list endpoints (e.g., default `limit=50, max_limit=100`).

---

## 3. Architecture Review Checklist
Before deploying or shipping new features, run through this checklist:
- [ ] No secrets or keys in source code.
- [ ] All inputs validated with Pydantic models.
- [ ] SQL queries use parameterized SQLAlchemy statements.
- [ ] Vector tables indexed with HNSW or IVFFlat.
- [ ] Long-running operations executed in background tasks.
- [ ] List APIs paginated with maximum limits.
- [ ] Sensitive endpoints protected by authentication/authorization.
