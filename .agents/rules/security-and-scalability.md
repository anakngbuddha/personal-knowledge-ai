---
trigger: always_on
description: Prioritize security hardening and architectural scalability across all code, database, and API designs.
---

# Security & Scalability Architecture Rules

Security and scalability are top architectural priorities for this codebase. All designs, API endpoints, database models, and background operations must uphold the following standards.

## 1. Security First Principles

1. **Authentication & Authorization**:
   - Secure all non-public API endpoints with proper token validation (e.g. JWT with cryptographic signature verification) and RBAC/ownership checks.
   - Enforce least privilege on all roles and data access scopes.
2. **Input Validation & Sanitization**:
   - Validate and constrain all inputs at API boundaries using Pydantic schemas.
   - Prevent SQL/NoSQL/Vector injection: always use parameterized queries and ORM abstractions (SQLAlchemy ORM/Core) — never interpolate raw strings into SQL queries.
3. **Secrets & Credentials Management**:
   - Never hardcode API keys, secrets, DB passwords, or credentials in source code.
   - Always load sensitive configuration via environment variables through `app.core.config.Settings`.
   - Ensure secrets are excluded from logs and error payloads.
4. **CORS, Headers & Rate Limiting**:
   - Maintain restrictive CORS policies (avoid wildcards in production).
   - Use standard security headers (Content Security Policy, X-Content-Type-Options, Strict-Transport-Security).
   - Implement rate limiting on sensitive, expensive, or AI generation endpoints.

## 2. Scalability & High-Performance Engineering

1. **Database & Vector Scalability**:
   - For `pgvector` embeddings, use proper indexing (e.g., HNSW with tuned `m` and `ef_construction` or IVFFlat) to prevent slow sequential table scans as vectors scale to millions.
   - Index all foreign keys, status flags, and queried columns.
   - Use SQLAlchemy connection pooling (`pool_size`, `max_overflow`, `pool_recycle`, `pool_pre_ping`).
2. **Asynchronous & Non-blocking I/O**:
   - Offload heavy compute, large file parsing (PDF, DOCX extraction), and embedding generation to background tasks or queue workers (FastAPI `BackgroundTasks`, Celery/Arq).
   - Keep request/response handlers snappy and non-blocking.
3. **Memory & Streaming**:
   - Stream large AI LLM responses and document downloads (`StreamingResponse`) instead of buffering gigabytes in memory.
   - Chunk files iteratively using generators rather than reading entire large files into a single in-memory buffer.
4. **Pagination**:
   - Enforce cursor-based or limit/offset pagination on all list queries. Never return unbounded collections.
5. **Caching**:
   - Cache expensive deterministic computations, repeated prompt embeddings, and metadata queries (Redis or in-memory caches with TTL).
