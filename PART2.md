ROLE
You are a senior full-stack engineer working in the repo anakngbuddha/personal-knowledge-ai
("SE Field Desk"): FastAPI + SQLAlchemy + Postgres/pgvector backend (backend/app), React/Vite
frontend (frontend/src), deployed on Render (API), Vercel (UI), Aiven (Postgres), Cloudflare R2.
Read AGENTS.md, Project_Plan.md, STATUS.md, USER_GUIDE.md and backend/app/{documents,retrieval,
generation,llm,catalog,playbooks,tools,notes,mcp} before changing anything.

PRODUCT GOAL
A personal knowledge workspace that feels like NotebookLM + Obsidian, usable by a non-technical
pre-sales engineer/salesperson:
1. The user uploads documentation (PDF first; also DOCX/PPTX/XLSX/text/URL) as extra knowledge.
2. The AI answers using: (a) the uploaded documents, (b) its own general knowledge, and
   (c) MCP tools (Brave Search, Microsoft 365, Playwright) when useful. Every answer clearly says
   which parts came from the user's documents (with citations), which is general knowledge, and
   which came from live web/tools.
3. The system builds a knowledge graph (products, vendors, capabilities, requirements, documents,
   notes) automatically from uploads, so retrieval and recommendations are faster and more
   accurate.
4. Answers are readable prose written for a salesperson, not fragmented, index-style output.
5. Reference scenario (must work end to end, see ACCEPTANCE TESTS): the user pastes a customer's
   requirements, then asks "what other solutions can I add from my product list?" and gets a
   tailor-fit recommendation combining Jabra, Shure, Poly and Huawei Cloud products with
   reasons, compatibility notes, gaps, and citations to the user's own documents.

HARD CONSTRAINTS
- Keep Postgres RLS, tenant scoping, the audit log and the prompt-injection containment
  (wrap_untrusted / SYSTEM_CONTRACT). Do not weaken existing security tests.
- Everything must run on free tiers: no native binaries on Render (no tesseract, no poppler);
  Gemini is the default LLM/embedding/OCR provider; keep the fake providers for tests.
- Do not break the existing test suite (backend/tests, scripts/run_eval_offline.py,
  scripts/run_golden_scenarios.py). Bump PROMPT_VERSION on every prompt change and update evals.
- Use plain language in all user-facing copy. No terms like chunk, ingest, MCP, RLS, dossier,
  ledger, collateral, hybrid search in the UI (use: Sources, Ask, Notes, Map, Connections).
- Small, reviewable commits per task below. Add or update tests for every backend change.
  Update USER_GUIDE.md to match reality. Remove tracked *.pyc files.

WORK IN THIS ORDER. Do not start a phase until the previous phase's acceptance checks pass.

PHASE 0: Unblock and secure (P0)
0.1 Auth: production must not run AUTH_MODE=owner_dev. Implement a simple single-owner login
    (passphrase or email + password via env-configured hash, or Supabase-style magic link if
    simpler) that issues the existing JWT. Add a login screen. Remove the insecure default for
    jwt_secret_key (fail fast when ENVIRONMENT=production and it is default). Update render.yaml
    and .env.example. Keep owner_dev for local dev/tests only.
0.2 Approval gate: add setting AUTO_APPROVE_UPLOADS (default true for single-owner mode). When
    on, uploaded documents become approved without requiring vendor/ownership/products/valid_until;
    those fields become optional enrichment, not gates. Keep the strict approval workflow available
    behind the setting for team use. Fix "metadata_complete" semantics accordingly.
0.3 Rename the concept in the UI from "approved collateral" to "Sources". If a source is excluded
    or unapproved, say so in plain words.
0.4 OCR: apply gemini-ocr.patch (OCR_PROVIDER=gemini). Then improve it: rasterize whole pages
    (pypdfium2, which is pip-installable and needs no system binary) when a page has no text layer
    and no embedded image; batch pages sequentially with a token-bucket rate limiter honoring Gemini
    free-tier limits; run OCR inside the background job with progress updates; make failures
    user-friendly ("This PDF is a scan and couldn't be read. Try again or upload a text version").
    Store OCR'd pages flagged ocr_applied so the UI can show "read with OCR".

PHASE 1: Human-readable answers (P0/P1)
1.1 Frontend: render assistant messages as Markdown (react-markdown + remark-gfm; sanitize).
    Turn [source_N] markers into small numbered citation chips that open the source passage
    (highlighted) in a side panel. Remove the "Query / Grounded" labels and the "claim withheld"
    banner. Show streaming tokens: use the existing streaming endpoint (stream: true, SSE) instead
    of stream:false.
1.2 New prompt version (4.0.0) with two answer modes selectable by a simple toggle in the chat
    ("From my sources only" / "Sources + expert knowledge"). Default = Sources + expert knowledge.
    - Write for a salesperson: conversational, well-structured prose with short headings/bullets
      only when helpful, a direct answer first, then reasoning, then next steps.
    - Citations are light-weight, placed at the end of a sentence or paragraph, not after every
      clause.
    - Label provenance in prose: "From your documents…", "From general product knowledge…",
      "From the web (Brave Search)…". Never present general knowledge as if it came from a document,
      and never invent specs, pricing or compatibility; flag unverified items as "verify with the
      vendor".
    - Strict mode keeps the old refusal behavior but with friendly wording and a suggestion of what
      to upload.
    - Never refuse just because retrieval is empty in expert mode. Answer from general knowledge,
      say no matching documents were found, and suggest what to upload.
1.3 Retrieval: (a) rewrite the user's question into a standalone query using conversation history
    before searching; (b) multi-query (generate 2-3 sub-queries for broad/compare questions);
    (c) add a lightweight reranker (LLM-based scoring of the top 30 down to 8-12, or Gemini
    ranking) behind a setting; (d) for "summarize/overview" questions, use per-document summaries
    (see 2.2) instead of random chunks.
1.4 Tools on by default: enable catalog/graph tools automatically; enable MCP tools automatically
    when the integration is configured and the question needs live/web/mail data. Keep a visible
    "Sources used: documents / graph / web / email" line under each answer.
1.5 Index Notes (see 4.2) so they are retrieved like documents.

PHASE 2: Smarter ingestion (P1)
2.1 Multi-file upload with drag-and-drop, folder support where the browser allows it, per-file
    progress (queued, reading, understanding, ready, failed with a plain-English reason and a
    Retry button).
2.2 After extraction, run an LLM "understand" step per document: document type, vendor(s),
    product names, version/date, a 5-8 sentence summary, key facts/specs table, and suggested
    tags. Store these; auto-fill vendor/products_referenced/valid_until when confidently found;
    show them in the source detail panel and let the user edit.
2.3 Structure-aware chunking: keep tables and spec sheets whole where possible, attach the section
    heading to every chunk, use larger parent + smaller child chunks (retrieve child, feed parent).
2.4 Show a "what I learned from this file" card after ingestion (summary + detected products +
    graph additions awaiting confirmation).

PHASE 3: Knowledge graph built from documents (P1)
3.1 Replace regex edge suggestion with LLM extraction run at ingestion time. For each document,
    extract entities (Vendor, Product, ProductFamily, Capability, UseCase, Requirement type,
    Certification/Platform such as Microsoft Teams, Zoom) and relationships with evidence quote,
    page reference and confidence. Auto-create missing Product/Vendor nodes as "suggested"; edges
    stay "pending" until one-click confirmation (bulk "accept all high-confidence" allowed).
    Keep the existing approve/reject model and RLS. Deduplicate via name/alias normalization
    (e.g., "Poly Studio X50" vs "Poly X50"). Keep the regex as a fallback.
3.2 Extend the model for how solutions are actually sold: new relation types recommended_with,
    cross_sell, upsell_to, certified_for, requires_license, bundle_component, suits_use_case;
    add nodes/attributes for UseCase/RoomType (huddle room, boardroom, contact center, home
    office), Platform (Teams, Zoom, Webex), and capability categories for audio, video, headsets,
    conferencing, cloud compute/storage/network/security, plus Huawei Cloud service families.
    Add a migration and update graph integrity checks.
3.3 Replace the fictional seed (Apex/Aegis/Nova...) with an empty catalog by default and an
    optional "Import my product list" flow (CSV/XLSX upload: name, vendor, category, description,
    key specs, price, platforms, notes; map columns in the UI). Keep the old seed only under a
    demo flag and make sure demo documents can never appear in real answers (mark is_demo and
    exclude in retrieval).
3.4 Product management UI: add/edit/delete products, capabilities, use cases and edges from the
    Map screen without touching Swagger. Include inline "add relationship" and a review queue for
    suggested nodes/edges.
3.5 Graph-aware retrieval (GraphRAG-lite): for a question, identify entities mentioned, expand 1-2
    hops in the graph (compatible, recommended_with, requires, conflicts_with), and add the linked
    products' best chunks/notes to the context; include the graph facts in the prompt as a
    structured "Known relationships" block.

PHASE 4: Advisor flow and Notes (the reference scenario) (P1)
4.1 Requirements memory: when the user pastes or uploads customer requirements, extract them with
    an LLM into a structured "Customer brief" (industry, size, rooms/users, platforms, cloud needs,
    budget, constraints, timeline, must-haves, nice-to-haves, exclusions). Store it as a Note
    linked to an optional Account, show it in the chat as an editable card, and keep it in context
    for the rest of the conversation. Replace regex extract_discovery_constraints with this
    (keep regex as validation for budget/seat numbers).
4.2 Gap analysis and recommendation: implement an "advisor" tool/playbook callable from chat that
    takes the Customer brief + the user's product list and returns: recommended bundle by
    requirement (with why), compatibility and conflict checks from the graph, what is missing
    from the product list, upsell/cross-sell options, questions to ask the customer, and
    assumptions to verify. Every recommendation cites the user's documents or is labeled general
    knowledge. Output as readable prose plus a compact table; offer "Export to Word/PowerPoint" and
    "Save as note".
4.3 Notes UI (Obsidian side): live markdown editor with [[wikilinks]] to products, accounts,
    notes and documents; backlinks panel; a graph view combining notes, sources and products;
    "Save this answer as a note" from chat. Embed and chunk notes on save so the AI can retrieve
    them.
4.4 Notebooks: add named notebooks/projects (e.g., per customer or deal) that scope sources,
    notes, chat and the Customer brief. Sources can be toggled on/off per notebook before asking.
4.5 Provide NotebookLM-style helpers: per-source summary, suggested questions, "Briefing",
    "FAQ", "Compare selected sources".

PHASE 5: UX rewrite for non-IT users (P1)
5.1 Replace the 01-08 numbered navigation with: Sources | Ask | Notes | Map | Connections |
    Settings. Move playbooks under Ask (as suggested actions), freshness watches under Sources,
    restore drills/SSO/ops under Settings > Admin.
5.2 Three-pane layout on Ask: Sources on the left with checkboxes, chat in the centre, a right
    panel for citations and saved outputs. Empty states and a first-run guide ("1. Add documents
    2. Add your products 3. Ask").
5.3 Plain-language errors everywhere. Wake-up state for Render cold start ("Waking the server, ~30
    seconds") with retry/backoff. Hide org IDs and roles unless in Settings > Admin.

PHASE 6: Quality, evals, ops (P1/P2)
6.1 Extend the eval set (evals/) with the reference scenario and 10+ salesperson-style
    questions; add checks for: readable prose, correct provenance labels, no fabricated specs, and
    graceful behavior when no source matches. Run on every prompt/model change.
6.2 Rate-limit/backoff wrappers for all Gemini calls (embeddings, OCR, understand, chat) with a
    shared limiter and visible queue status. Make the background worker resilient to Render
    restarts (resume incomplete jobs on boot).
6.3 Add .gitignore entries and remove tracked .pyc files. Add a health page showing DB, storage,
    LLM key, OCR provider and worker status. Rewrite USER_GUIDE.md for non-technical users.

ACCEPTANCE TESTS (automate with the fake provider and add a manual Gemini smoke script)
A. Upload a text PDF and a scanned PDF (no text layer). Both reach "ready" without touching
   metadata or Swagger, the scan is marked "read with OCR", and a question about either returns a
   readable answer with citations. Answers contain no raw "[source_N]" text and no unrendered
   markdown.
B. Ask a question whose answer is NOT in any document. Expert mode answers from general
   knowledge with a clear label and a suggestion of what to upload; strict mode says so
   politely. Neither returns an empty refusal banner.
C. Follow-up question ("what about the pricing?") retrieves correctly using conversation history.
D. Upload 3 vendor PDFs (Jabra, Shure, Poly) and 1 Huawei Cloud PDF. After ingestion the Map
   shows the vendors/products as suggested nodes and cross-vendor edges with evidence; the user
   accepts them in one click.
E. Import a product list CSV of ~30 products. Then in one chat: (1) paste customer requirements
   (e.g., 12 huddle rooms on Teams, a 40-seat contact center needing headsets, ceiling mics for a
   boardroom, backup/DR on Huawei Cloud); (2) ask "what solutions can I add from my product list
   based on these requirements?" The answer must: restate the requirements briefly; recommend
   specific products from the list with reasons; cite the uploaded docs where used; flag
   conflicts/compatibility issues from the graph; list gaps not covered by the product list;
   suggest upsell/cross-sell; and offer export or save-as-note.
F. Production mode refuses unauthenticated API calls (401) and the login works in the UI.
G. Existing backend tests and golden scenarios still pass; new tests cover every task.

DELIVERABLES
Working code on a branch with one commit per numbered task, updated migrations, updated tests,
updated USER_GUIDE.md and render.yaml, and a CHANGELOG.md summarizing what changed, new env vars,
and how to deploy. If any task is ambiguous or has a trade-off, choose the simplest option that
satisfies the acceptance tests and note the decision in the changelog rather than stopping to ask.