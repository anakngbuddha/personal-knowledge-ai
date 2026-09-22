Build Brief: personal-knowledge-ai → "Obsidian + NotebookLM"
Repo: github.com/anakngbuddha/personal-knowledge-ai Use this whole document as the system/task prompt for Claude Code (or any coding agent) working in this repo. It reflects a full code-level audit already done — don't re-diagnose these issues, fix them.

Goal
Make this app actually feel like NotebookLM (ask questions over your uploaded files, get cited answers) fused with Obsidian (linked notes with a graph view) — for one user's personal/presales knowledge base. Most of the scaffolding for both already exists in this repo; the two features that make each product feel like itself are the ones missing or broken. Fix those first. Do not rebuild what already works.

This is not a request to build a new enterprise SE platform. Enterprise features (RFP Responder, Incident Triage, SSO, restore drills, freshness monitoring) already exist and work structurally — they are out of scope for this pass. Don't expand them, and don't let them block the two core features.

Context (ground truth from the audit — trust this, don't rediscover it)
Stack: FastAPI + Python backend, React + TypeScript + Vite frontend, PostgreSQL + pgvector, Gemini for both embeddings and generation (GEMINI_API_KEY, gemini-embedding-001, gemini-2.5-flash), Cloudflare R2 for file storage. Backend deploys to Render (runtime: python, render.yaml, free tier). Frontend deploys to Vercel (vercel.json).

Current state: STATUS.md marks all 10 phases "Done." This is not accurate. Specifically:

backend/app/generation/service.py — ask() and ask_stream() are stubs that raise NotImplementedError(...). backend/app/api/routes/ask.py calls these directly for both /ask and /conversations/{id}/ask. This is why Grounded Ask returns nothing. A dead GenerationService class further down the same file hardcodes an Anthropic client (claude-3-5-sonnet-20241022) — it is not wired to any route and is inconsistent with the rest of the app, which uses app.llm.factory.get_llm_provider() → Gemini. Delete that class when you fix this file; don't extend it.

frontend/src/services/http.ts's request() wraps every call in a 15s AbortController and collapses every failure mode (real network error, CORS, timeout) into one message: "could not reach the API". This is why requests fail with nothing in the browser console. render.yaml sets GEMINI_RPM: "10", and backend/app/embeddings/gemini.py retries 429/5xx with exponential backoff (up to 5 attempts, 2s–60s) — a single retried embed call can outlast the 15s client timeout on its own.

backend/app/mcp/servers.py launches Playwright MCP via npx -y @playwright/mcp@latest --headless. render.yaml provisions a Python-only build (pip install -r requirements.txt, no Node toolchain, no Chromium). This server cannot start in the current deploy target.

backend/app/retrieval/search.py only queries DocumentChunk/Document. Notes are indexed (backend/app/notes/index.py, index_note()) but confirm they're reachable through the same predicate-filtered candidate set. The product catalog (backend/app/catalog/models.py — Product, ProductEdge) is not searchable through /search or /ask at all today.

backend/app/retrieval/rewrite.py does no semantic query understanding. Follow-up detection is regex on literal English phrases; "broad query expansion" appends two hardcoded strings ("specifications compatibility", "recommended products") regardless of actual content.

frontend/src/components/GraphExplorer.tsx only renders the product catalog graph. There is no visual graph for notes, even though the backend already has the data for one (Note, NoteLink, backlinks() in backend/app/notes/service.py).

Notes editor (NotesEditor.tsx) has no wikilink autocomplete and no backlinks panel, even though [[wikilinks]] are parsed and resolved server-side (backend/app/notes/wikilinks.py).

What already works well and must be preserved, not rebuilt:

Permission-aware retrieval where filters apply before fusion structurally (see the search.py docstring) — both branches read from one filtered candidate CTE.
Prompt-injection containment (backend/app/documents/injection.py) — nonce-fenced untrusted content, delimiter neutralization applied at ingest time, explicit separation between real containment (wrap_untrusted) and non-blocking observability (scan_for_injection).
Multi-format ingestion (PDF, DOCX, PPTX, XLSX, MD, TXT, HTML) with citation anchors down to page/slide/sheet+cell (backend/app/documents/extraction.py, sniffing.py).
The tool registry (backend/app/tools/registry.py) already defines hybrid search, catalog/graph queries, and MCP tool calling as allowlisted, Pydantic-validated tools — this is the scaffold for the "one chat station" experience; it just isn't called by anything yet.
JWT auth + org/workspace scoping + Postgres RLS — all new work must stay inside this, not route around it.
Do's
Implement generation/service.py by calling app.llm.factory.get_llm_provider(), wrapping every retrieved chunk with wrap_untrusted() from documents/injection.py, and — when enable_tools is true — looping through tools/registry.py's execute_tool(). Yield/return values must match what ask.py's _stream_response and _answer_to_out already expect (delta, done, citations, conversation_id, message_id, refused, usage) so the frontend needs no changes.
Once generation works, route it through notes and the product catalog too, not just uploaded documents, so one answer can cite a PDF, a personal note, and a catalog entry together.
Add notes and the product catalog as additional branches in retrieval/search.py, going through the same permission-filtered candidate set as documents — do not bypass build_predicate_set/assert_enforced for the new branches.
Replace retrieval/rewrite.py's regex logic with an LLM-based rewrite once generation is available.
Build a graph view for notes, reusing GraphExplorer.tsx's rendering approach but pointed at NoteLink/backlinks() data.
Add [[ wikilink autocomplete (query existing notes/products as the user types) and a backlinks panel to NotesEditor.tsx/NotesPanel.tsx.
Surface rrf_score/branch_scores (already returned by the backend) in SearchExplorer.tsx.
Fix http.ts to report the real failure (status code, timeout vs. network error) instead of one generic message; make the timeout endpoint-appropriate rather than a single global 15s.
Disable Playwright MCP by default until a Node/Chromium runtime is actually available at the deploy target; don't leave it silently failing in the tool loop.
Simplify primary navigation to plain language ("Ask," "Notes," "Sources," "Connectors") and move RFP/Incident Triage/Upgrade Impact/SSO/Ops out of primary nav into a clearly separate section.
Write or extend tests in backend/tests for every fix, and run scripts/run_golden_scenarios.py / the existing eval suite before calling something done.
Work in small, verifiable increments: implement one item, confirm it end-to-end (upload → ask → correct cited answer, or write a note → see it in the graph), then move to the next.
Don'ts
Don't rewrite the retrieval or security architecture from scratch — it's sound; extend it.
Don't introduce a second LLM provider or hardcode a model — use the existing llm_provider/embedding_provider factory pattern so Gemini stays the single source of truth.
Don't weaken or bypass wrap_untrusted() when wiring generation — document content must never reach the model unfenced.
Don't swallow errors into generic messages anywhere, frontend or backend.
Don't build toward local-first/offline storage in this pass — that's a separate architectural decision (different client, local embeddings) that hasn't been made yet; stay on the current hosted Postgres + R2 model.
Don't add new enterprise-workflow features or expand existing ones (RFP, incident triage, SSO, freshness, restore drills). Deprioritizing their visibility is in scope; adding to them is not.
Don't re-enable Playwright MCP as a default-on integration until its runtime dependency is actually solved.
Don't mark anything "Done" in STATUS.md (or claim a fix is complete) without a real end-to-end pass — upload a file, ask a question about it, confirm the citation is correct.
Don't touch RLS/org/workspace scoping to make a feature "simpler" — every new query must stay principal-scoped.
Constraints
Backend runtime: Render, runtime: python, pip install -r requirements.txt only — no Node/npm available unless a build step is explicitly added.
Frontend runtime: Vercel, npm install && npm run build, output dist/.
LLM/embeddings: Gemini only, via the existing factory pattern (llm/factory.py, embeddings/factory.py). Current rate limit GEMINI_RPM=10 — raise this or add explicit user-facing progress state; don't just extend timeouts and hope.
Database: Postgres + pgvector, RLS-enforced, multi-tenant (org_id/workspace_id). All new tables/queries must respect this.
Auth: JWT + existing Principal/role model (security/deps.py, security/principal.py) — reuse it, don't parallel it.
Frontend patterns: existing services/api.ts + services/http.ts request layer, existing component structure — extend, don't introduce a new state-management or data-fetching library.
Testing: backend/tests, docs/eval, scripts/run_golden_scenarios.py already exist — new work should pass against them, not sidestep them.
Maintainer: effectively solo (Mark). Prioritize a small number of fully-working, end-to-end slices over broad, partially-working coverage.
Definition of done (acceptance criteria)
Upload a PDF, MD, XLSX, or PPTX file. Ask a question about its content in Grounded Ask. Receive a real, synthesized answer (not a template, not an error) with an accurate citation, within a reasonable time, with no silent failures.
Write a note containing a [[wikilink]] to another note or product. The link resolves, autocompletes while typing, and shows up as a backlink on the target.
A graph view exists showing how notes connect to each other (and ideally to products), separate from the product-catalog-only graph that exists today.
Asking a question can draw evidence from an uploaded document, a personal note, and the product catalog in the same answer — not just documents.
Nothing in STATUS.md claims "Done" unless a person can reach it from the UI and it works.
Suggested sequencing
Fix generation/service.py (unblocks everything else).
Fix frontend error handling + timeout / rate-limit mismatch.
Disable Playwright MCP by default.
Add notes + catalog to hybrid search.
Replace regex query rewriting with LLM-based rewriting.
Build the notes graph view.
Add wikilink autocomplete + backlinks panel.
Surface retrieval scores in the UI.
Simplify navigation; move enterprise features out of primary nav.