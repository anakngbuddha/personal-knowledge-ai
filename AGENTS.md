# Workspace Rules - Personal Knowledge AI

This file defines project-wide development rules for AI pair programmerstest operating in this repository.

## 1. Graphify Knowledge Graph (Active & Enforced)
- **Prompt Trigger**: On every incoming prompt, consult the Graphify knowledge graph under `graphify-out/graph.json` or query it via CLI (`python -m graphify query "<topic>"` or `path` / `explain`). Do this before proposing architecture changes or exploring random files.
- **Automatic Graph Update**: Every time code files are modified, created, or deleted, immediately update the knowledge graph:
  ```bash
  python -m graphify update .
  ```
  (This is AST-only, takes ~1-2 seconds, and costs zero API tokens). The `.agents/hooks.json` lifecycle hook also triggers this automatically on file edits.

## 2. Test & Verification Guarantee
- **Verify Every Modification**: Never finish a task involving code modifications or feature updates without running verification checks:
  ```bash
  python scripts/verify_project.py
  # or specifically for backend unit tests:
  python -m pytest backend/tests
  ```
- Any new features or changes must include matching unit tests in `backend/tests/`.
- Ensure all Python files pass syntax compilation and frontend builds cleanly (`tsc -b`).

## 3. Security & Scalability Priorities
- **Security**:
  - OWASP Top 10 compliance: zero hardcoded secrets; validate all inputs using Pydantic; prevent SQL/vector injection using SQLAlchemy parameterized queries.
  - Require authentication and authorization tokens on sensitive API endpoints.
  - Configure secure CORS and rate limiting on resource-intensive endpoints.
- **Scalability**:
  - Vector indexing: use HNSW or IVFFlat indexes on `pgvector` columns.
  - Connection pooling: optimize SQLAlchemy pool sizes for concurrent traffic.
  - Asynchronous background execution: process document extractions, chunking, and embedding workflows asynchronously.
  - Memory efficiency: stream LLM completions and chunk documents lazily without buffering unbounded payloads.
  - Always paginate list endpoints.
