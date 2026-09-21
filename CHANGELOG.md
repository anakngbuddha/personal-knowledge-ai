# Changelog

All notable changes to the Field Desk, newest first.

This file is the record the build plan asks for: what changed, which trade-off was
taken where the plan left a choice open, which environment variables are new, and how
to deploy. One entry per numbered task.

---

## Unreleased — NotebookLM + Obsidian Field Desk

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

---

## Decisions recorded

The plan allows the simplest option that satisfies the acceptance tests. These are the
choices taken, so nobody has to re-derive them from the diff.

| Decision | Choice |
|---|---|
| Tools plus streaming | The tool round runs first, then the final prose is streamed. `/ask` no longer rejects `stream` and `enable_tools` together. |
| Gemini OCR transport | `httpx`, reusing the existing Gemini client. No `google.generativeai`. |
| Prompt version | Bumped to `4.1.0` when the expert/strict copy was rewritten. `4.0.0` was already the label but was never wired. |
| Understand-step prompt version | Tracked separately as `UNDERSTAND_PROMPT_VERSION`, so a summarizer tweak does not invalidate answer-prompt evals. |
| Understand-step fallback | If the model returns prose instead of JSON, a deterministic heuristic fills the same fields. Ingestion never fails because a summary could not be parsed. |
| Parent/child chunk storage | Parent passage and table flag live in the existing chunk metadata rather than new columns, so the change needs no migration. |
| Demo catalog | Seeded only behind `DEMO_SEED_CATALOG`. Golden and eval tests keep using seed fixtures in-process. |
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
| `GEMINI_RPM` | `10` | Shared token bucket for embeddings, OCR, understand, and chat. |

## Deploying

* **Backend (Render).** `render.yaml` carries `AUTH_MODE=jwt`, `OCR_PROVIDER=gemini`,
  and `AUTO_APPROVE_UPLOADS`. Set `JWT_SECRET_KEY` (32+ characters), `DATABASE_URL`,
  `GEMINI_API_KEY`, and the R2 credentials as secrets. Boot runs extensions, tables,
  and idempotent migrations.
* **Frontend (Vercel).** `npm run build` in `frontend/`. Set `VITE_API_BASE_URL` to
  the Render URL. The first request after an idle period wakes the server, which the
  UI now says out loud instead of timing out.
