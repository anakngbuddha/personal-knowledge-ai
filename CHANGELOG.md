# Changelog

All notable changes to the Field Desk, newest first.

This file is the record the build plan asks for: what changed, which trade-off was
taken where the plan left a choice open, which environment variables are new, and how
to deploy. One entry per numbered task.

---

## Unreleased — NotebookLM + Obsidian Field Desk

### Phase 6.3 — Ops hygiene

* Removed tracked `__pycache__/*.pyc` from git (ignore rules already covered them).
* `/health/dependencies` reports LLM key configured (boolean only, never the secret).
* Settings > Admin **System status** shows database, file storage, AI key, OCR, and background jobs in plain language.
* `USER_GUIDE.md` rewritten for non-technical users; deploy/local detail points to `README.md` / `.env.example`.

### Phase 6.2 — Shared Gemini limiter and job resume

* All Gemini paths (embeddings, chat sync/stream, OCR) call `acquire_gemini()` on the shared token bucket. OCR retries on 429.
* App boot runs `reap_stale` before workers start so Render restarts reclaim abandoned file jobs.
* `/health/dependencies` reports `gemini.queued`. Settings > Admin shows AI wait queue and file reading counts.
* No new environment variables (`gemini_rpm` already existed).

### Phase 6.1 — Salesperson evals

* Added `docs/eval/salesperson_set.json` (reference scenario E + 13 salesperson cases).
* Scorer in `backend/app/eval/salesperson.py`: prose (no jargon), provenance labels, catalog grounding, empty-retrieval expert vs strict.
* `scripts/run_generation_eval.py` runs the suite with the fake provider and exits non-zero on failure. Re-run after every `PROMPT_VERSION` change.
* Pytest gate: `backend/tests/test_salesperson_eval.py`.
* Eval home stays `docs/eval/` (not a top-level `evals/` folder).

### Phase 4.4 — Notebooks

* Named notebooks live inside the existing workspace. They are not extra workspaces.
* A new notebook switches on every current non-demo source. Sample files stay off.
* Notes, customer briefs, and new chats store `notebook_id`. Older rows with a null id stay visible when no notebook is selected.
* Ask uses the saved on/off set. An empty set searches nothing, so expert mode can still answer from general knowledge.
* Migration `0019_notebooks`. No new environment variables.

### Phase 4.5 — Source helpers

* **Briefing**, **FAQ**, and **Compare** use the stored summary and key facts. They do not re-read the file.
* Suggested questions are cached on the source after the first request.
* Studio prompts use `STUDIO_PROMPT_VERSION` (`1.0.0`). The answer prompt stays `4.2.0`.
* The offline model still returns a deterministic write-up built from those summaries.

### Phase 5.1 — Navigation

* The numbered rail is now **Sources**, **Ask**, **Notes**, **Map**, **Connections**, and **Settings**.
* Suggested actions sit under Ask. Page watches sit under Sources. Restore drills and company sign-in sit under Settings > Admin.

### Phase 5.2 — Ask layout

* Ask is three panes: sources with checkboxes, the conversation, and citations plus saved notes.
* Empty states point at adding documents, adding products, then asking.

### Phase 5.3 — Plain errors and wake-up

* Failed requests show one plain sentence. Raw errors, SQL, and ids stay off the screen.
* A cold server shows “Waking the server, ~30 seconds” and retries health for about half a minute.
* Role and workspace name appear only under Settings > Admin.

### Decisions

* Notebooks are a new table, not a second workspace.
* `playbooks/brief_api.py` stays unwired. The customer brief API remains `/advisor/brief`.
* No new environment variables for 4.4–5.3. Deploy by running migrations on boot (`0019_notebooks`) and rebuilding the frontend.

### Goal 2 — unblock Vercel

* **fix: close template strings in `api.ts`.** Four request paths opened with a
  backtick and closed with a double quote, so `tsc -b` failed and the production UI
  never built. Repaired the approve, reject, freshness check, and alert ack paths and
  swept the rest of the frontend for the same mistake (none found elsewhere).

### Phase 0 — unblock and secure

* **0.1 Auth.** `USER_GUIDE.md` and `.env.example` now document the login/signup flow
  instead of the retired `/auth/token` path. Production refuses to boot with a missing
  or short `JWT_SECRET_KEY`, unauthenticated `/ask` is `401`, and `owner_dev` is kept
  for tests and CI only.
* **0.2 Approval gate.** `auto_approve_uploads` was defined but never read. It is now
  wired through `documents/service.py` and `documents/metadata.py`. With it on (the
  default) a new upload becomes `approved` immediately, and vendor / ownership /
  products / `valid_until` become optional enrichment: `metadata_complete` is a chase
  list, not a retrieval gate. With it off, the old strict promotion gate is unchanged.
  This is what makes "upload, then ask" work, because generation defaults to
  `approved_only=True`.
* **0.3 Sources wording.** User-visible "collateral", "dossier", and bare "approved"
  became **Sources** with plain-language status. A source that is excluded from an
  answer says so in words.
* **0.4 OCR.** Added `pypdfium2` (pip only, no poppler, no native tesseract) so a page
  with no text layer and no embedded image can be rasterized and read. Gemini OCR is
  implemented over the existing `httpx` client rather than `google.generativeai`, so
  no Google SDK enters `requirements.txt`. Pages are processed sequentially behind a
  token bucket for the free tier, progress lands on the job row, `ocr_applied` is kept
  so the UI can say "read with OCR", and a scan that still cannot be read returns
  "This PDF is a scan and couldn't be read. Try again or upload a text version."

### Phase 1 — human-readable answers

* **1.1 Frontend answers.** Markdown rendering with `react-markdown`, `remark-gfm`,
  and `rehype-sanitize`. `[source_N]` markers are parsed into numbered chips that open
  the passage in a side panel and are stripped from the visible prose. Chat streams
  over SSE through `api.askStream`; nothing sends `stream:false` any more.
* **1.2 Prompt 4.1.0.** `strict_mode` is passed into `generation_ask` and
  `system_prompt_for`, which it previously was not. Expert and strict copy were
  rewritten for salesperson prose: direct answer, then reasoning, then next steps,
  with light citations and explicit provenance sentences. Expert mode no longer
  refuses on empty retrieval. Toggle copy is "From my sources only" and "Sources +
  expert knowledge", defaulting to expert.
* **1.3 Retrieval.** Follow-up questions are rewritten against conversation history
  before search, broad compare/overview questions expand into two or three
  sub-queries, and the fused candidate set is reranked down to the context budget
  behind `GENERATION_RERANK_ENABLED` (default on, deterministic in tests).
* **1.4 Tools by default.** `enable_tools` defaults to true; MCP-backed tools are only
  offered when the integration is configured. Each answer reports "Sources used" in
  plain words (documents / notes / graph / web / email), never "MCP".
* **1.5 Notes in retrieval.** Saving a note chunks and embeds it into the same corpus
  as documents, so Ask can cite tribal knowledge. Deleting a note drops its index.

### Phase 2 — smarter ingestion

* **2.1 Multi-file upload.** Drag-and-drop, multi-select, and whole-folder drop where
  the browser supports it. Every file gets its own row with a plain-language state
  (queued, reading, understanding, ready, failed) and its own Retry, so one bad file
  never sinks the batch. States are polled from the per-document status endpoint.
* **2.2 Understand step.** After extraction each source is summarized once into
  structured JSON: type, vendors, products, version label, validity date, a short
  summary, key facts, and tags, with a confidence score. High-confidence vendor,
  products, and `valid_until` are auto-filled and stay editable in the source detail
  panel.
* **2.3 Structure-aware chunking.** Tables and spec sheets are kept whole instead of
  being split mid-row, every child chunk carries its section heading, and the parent
  passage is stored alongside the child so retrieval can match narrowly and prompt
  with full context.
* **2.4 What I learned.** When a source turns ready, its summary, detected products,
  key facts, and any pending map suggestions are shown as a card.

### Phase 3 — the product map, read out of the sources

* **3.2 Selling model.** Seven relationships a salesperson actually uses were added to
  the map: `recommended_with`, `cross_sell`, `upsell_to`, `certified_for`,
  `requires_license`, `bundle_component`, `suits_use_case`. Use cases, room types and
  platforms became one `selling_contexts` table with a reviewed `product_context_links`
  table beside it, capability categories were given canonical buckets (audio, video,
  headsets, conferencing, Huawei Cloud → cloud), and fourteen integrity tests fail the
  moment the Python constants, the CHECK constraints, and migration `0017` drift apart.
  Done before 3.1 on purpose: extraction cannot propose a vocabulary that does not exist.
* **3.1 Read the map out of a source.** Regex-only curation could only find a
  relationship when a sentence matched one of seven patterns *and* both products were
  already in the catalog, which is exactly wrong for a brand new vendor PDF. The read
  step now asks the model for products, contexts and relationships with a quote, a page
  and a confidence, fenced through `wrap_untrusted`. Unknown relation names are dropped
  rather than guessed, a relationship with no quote is dropped, names are deduplicated
  against the map, everything lands as `suggested` / `pending_review`, and the regex
  pass stays as the deterministic fallback. Runs after a source is ready, so it can
  never fail an upload. Adds a review queue and one-click "accept all high-confidence".
* **3.3 Empty product list, and import your own.** The sample catalog no longer loads
  itself into every workspace. It is available only behind `DEMO_SEED_CATALOG`, and
  everything it writes is stamped `is_demo`, including collateral: retrieval drops demo
  sources through a corpus predicate, so sample material can never be quoted back as if
  it were the customer's own. "Import my product list" reads a CSV or XLSX, guesses what
  each column means, shows the guess for confirmation, normalises local spellings
  ("Partner" → resold, "end of life" → EOL, "on premise" → on-prem), and reports every
  row it had to drop and why. Re-importing fills blanks instead of duplicating the map.
* **3.4 Edit the map.** Use cases, room types, platforms and their links to products
  gained full CRUD, so correcting the map no longer means opening Swagger. The Map
  screen can add a product, rename or remove one, add a relationship inline with its
  evidence, and work through the review queue. Every relationship is offered in the
  words it reads as, never as a relation name.
* **3.5 GraphRAG-lite.** When a question names a product the map knows, the accepted
  relationships one or two hops out are stated in the prompt as plain sentences, and the
  best passage for each neighbour is retrieved as well, so a pairing can be cited rather
  than asserted. Only approved relationships are walked: a suggestion nobody accepted is
  not a fact. The block carries quotes lifted from uploaded documents, so it is fenced
  like any other passage. Prompt version bumped to `4.2.0`.

---

## Decisions recorded

The plan allows the simplest option that satisfies the acceptance tests. These are the
choices taken, so nobody has to re-derive them from the diff.

| Decision | Choice |
|---|---|
| Tools plus streaming | The tool round runs first, then the final prose is streamed. `/ask` no longer rejects `stream` and `enable_tools` together. |
| Gemini OCR transport | `httpx`, reusing the existing Gemini client. No `google.generativeai`. |
| Prompt version | `4.1.0` when the expert/strict copy was rewritten, `4.2.0` when the known-relationships block was added. |
| Understand-step prompt version | Tracked separately as `UNDERSTAND_PROMPT_VERSION`, so a summarizer tweak does not invalidate answer-prompt evals. |
| Understand-step fallback | If the model returns prose instead of JSON, a deterministic heuristic fills the same fields. Ingestion never fails because a summary could not be parsed. |
| Parent/child chunk storage | Parent passage and table flag live in the existing chunk metadata rather than new columns, so the change needs no migration. |
| Phase 3 task order | 3.2 shipped before 3.1: the read step cannot propose relationships the database would reject. |
| Demo catalog | Seeded only behind `DEMO_SEED_CATALOG`. Golden and eval tests keep calling `seed_phase4_catalog` in process, so it was left untouched. |
| Marking sample rows | The seed is diffed before and after instead of threading an `is_demo` flag through every row it builds. Keeps the seed fixtures byte-identical for the eval suite. |
| Import is two requests | Preview and import each carry the file. Holding a parsed spreadsheet in memory between two requests loses the import to a free-tier restart. |
| Unreadable import values | A value we do not recognise falls back to the safe default rather than failing the row. A spreadsheet full of local spellings should still import. |
| Map editing endpoints | A separate `/map` router rather than more surface on the catalog router: this is the screen's write path, not another catalog API. |
| Map expansion depth | Two hops, six neighbours, one passage each. Enough to answer "what else do I need", small enough to leave the context budget for the question. |
| PPT export | `python-pptx` over the same advisor payload as the DOCX export. |

## New environment variables

| Variable | Default | What it does |
|---|---|---|
| `AUTO_APPROVE_UPLOADS` | `true` | New uploads are usable immediately; metadata becomes optional enrichment. |
| `OCR_PROVIDER` | `none` (`gemini` on Render) | Reads scanned PDFs. `gemini` needs `GEMINI_API_KEY`. |
| `GENERATION_RERANK_ENABLED` | `true` | Reranks the fused candidate set before prompting. |
| `GENERATION_RERANK_CANDIDATES` | `30` | How many candidates to rerank down from. |
| `DOCUMENT_UNDERSTANDING_ENABLED` | `true` | Runs the 2.2 understand step at ingest. |
| `UNDERSTANDING_MIN_CONFIDENCE` | `0.7` | Above this, detected vendor / products / validity are auto-filled. |
| `UNDERSTANDING_MAX_CHARS` | `12000` | How much of a source the understand step reads. |
| `CHUNK_PARENT_CHILD_ENABLED` | `true` | Retrieve the child chunk, prompt with the parent passage. |
| `CHUNK_KEEP_TABLES_WHOLE` | `true` | Never split a table or spec sheet mid-row. |
| `GRAPH_EXTRACTION_ENABLED` | `true` | Reads products and relationships out of each new source (3.1). |
| `GRAPH_EXTRACT_MAX_CHARS` | `16000` | How much of a source the map read looks at. |
| `GRAPH_AUTO_ACCEPT_CONFIDENCE` | `0.85` | The bar for "accept all we are confident about". |
| `DEMO_SEED_CATALOG` | `false` | Makes the sample product list loadable. Off means the product list starts empty. |
| `CATALOG_IMPORT_MAX_ROWS` | `2000` | Rows read from an imported product list. |
| `CATALOG_IMPORT_MAX_BYTES` | `5242880` | Size limit for an imported product list. |
| `GRAPH_EXPANSION_ENABLED` | `true` | Lets an answer use the map, not only the passages (3.5). |
| `GRAPH_EXPANSION_HOPS` | `2` | How far out from a named product to walk. |
| `GRAPH_EXPANSION_MAX_NEIGHBOURS` | `6` | How many linked products an answer may pull in. |
| `GRAPH_EXPANSION_CHUNKS_PER_NEIGHBOUR` | `1` | Passages retrieved per linked product. |
| `GEMINI_RPM` | `10` | Shared token bucket for embeddings, OCR, understand, and chat. |

## Deploying

* **Backend (Render).** `render.yaml` carries `AUTH_MODE=jwt`, `OCR_PROVIDER=gemini`,
  `AUTO_APPROVE_UPLOADS`, and `DEMO_SEED_CATALOG=false`. Set `JWT_SECRET_KEY`
  (32+ characters), `DATABASE_URL`, `GEMINI_API_KEY`, and the R2 credentials as
  secrets. Boot runs extensions, tables, and idempotent migrations, including `0018`,
  which adds `documents.is_demo`.
* **Frontend (Vercel).** `npm run build` in `frontend/`. Set `VITE_API_BASE_URL` to
  the Render URL. The first request after an idle period wakes the server, which the
  UI now says out loud instead of timing out.
