You are implementing three feature changes to the personal-knowledge-ai repo
(anakngbuddha/personal-knowledge-ai). Follow the existing conventions in
.agents/rules/security-and-scalability.md and .agents/rules/verification.md —
background jobs for heavy compute, Pydantic validation at API boundaries,
pytest coverage for every new behavior, and run `python -m pytest backend/tests`
before declaring anything done. Preserve backward compatibility: existing
CSV/XLSX RFP uploads and existing freshness single-URL checks must keep working
exactly as they do today.

============================================================
GOAL 1 — RFP intake: accept PDF (OCR) and index it like everything else
============================================================

Current state: `rfp.parse` in backend/app/playbooks/rfp.py calls
`parse_spreadsheet()`, which only handles CSV/XLSX and throws on anything else.

Changes:

1. Extend `rfp.parse` to detect file type (reuse `documents/sniffing.py`'s type
   detection) and branch:
   - csv/xlsx → existing `parse_spreadsheet()` path, unchanged.
   - pdf/docx → run `documents.extraction.extract(data, file_type)` (this
     already OCRs scanned PDF pages via `_ocr_pdf_pages`, do not reimplement
     OCR). This returns `Block` objects, not requirement rows.

2. Add a new requirement-segmentation step for the pdf/docx path, since OCR
   text is prose, not rows. Given the concatenated block text, produce the
   same `{id, text, section, must_have}` shape `parse_spreadsheet()` produces.
   Use an LLM call for this (batch the document text, ask for a JSON array of
   requirement objects — follow the same containment pattern as
   `documents/understanding.py`: wrap source text with `wrap_untrusted()` from
   `documents/injection.py`, and if the model call fails or returns invalid
   JSON, do not crash the run — fall back to a deterministic heuristic
   (e.g., split on sentences containing "must"/"shall"/"required" as a floor,
   same "ingestion never fails" philosophy as `understanding.py`).

3. Also index the parsed RFP document itself into the existing embedding
   system so ad-hoc user queries against it are answerable, not just the
   row-by-row workflow. Reuse the existing pipeline as-is rather than
   reimplementing it: call `documents.service.create_document()` with the
   uploaded bytes, then `enqueue_ingestion()` — this already runs
   `chunk_blocks()` → `understand_source()` → `get_embedding_provider().embed_documents()`
   → `DocumentChunk` storage (see `process_document()` in
   backend/app/documents/service.py for the exact sequence; do not duplicate
   this logic inside rfp.py, call into it).
   Tag the created Document's metadata (source_type or similar) as
   "rfp_intake" so it's identifiable, and decide + implement whether it should
   be `approved_only` for citation purposes like other uploads or excluded
   from the general KB (default: excluded from general retrieval, since it's
   a client's incoming requirements doc, not your own collateral).

4. Route the OCR/extraction call through the existing background job queue
   (backend/app/jobs/queue.py, jobs/worker.py) rather than inline in the
   request handler, per the scalability rule on heavy file parsing.

5. Tests: add fixtures for a text-layer PDF, a scanned/OCR PDF, and a DOCX RFP
   in backend/tests, covering both the segmentation output shape and that
   parse_rfp still returns identical results for existing CSV/XLSX fixtures.

============================================================
GOAL 2 — RFP hazy/semantic matching + LLM-backed drafting
============================================================

Current state: `rfp.evaluate` matches requirements to catalog products/
capabilities via literal token-set overlap (`_tokenize()` intersection) —
"Azure Blob Storage" will never match "OBS" this way. `rfp.draft` → `_draft_one`
is pure deterministic Python with zero LLM calls, despite `draft_responses`
already calling `check_rate_limit()` and `check_token_budget()` as if it
spends budget.

Changes:

1. In `rfp.evaluate`, add embedding-similarity candidate matching alongside
   (not instead of — keep both as signals) the existing token overlap:
   - Embed each requirement's text once via `get_embedding_provider()`
     (backend/app/embeddings/factory.py — same provider used everywhere else).
   - Embed each catalog Product's `name + description` (cache/reuse embeddings
     where possible rather than recomputing every run — batch this per RFP
     run, not per requirement, to control cost).
   - Rank candidates by cosine similarity, take top-N (e.g. 5) as
     `candidate_products`, merging with (not replacing) the exact
     token-overlap matches — union the two lists, dedupe by product id, and
     tag each candidate with which signal(s) found it (exact_match,
     semantic_match, or both). This tag matters for auditability in step 3.

2. Give `rfp.draft`'s `_draft_one` an actual LLM call. Replace the pure-Python
   status/response logic with: given the requirement text, the shortlisted
   candidate products (with descriptions and the match-signal tags from step 1),
   and the evidence hits from `rfp.retrieve` (already semantic — hybrid_search_tool
   uses pgvector + keyword fusion, no change needed there), prompt the model to:
   - decide Compliant / Partial / Non-Compliant
   - select which product(s) satisfy the requirement
   - write the response text, explicitly naming any cross-vendor/naming
     equivalence reasoning it used (e.g., "OBS is functionally equivalent to
     Azure Blob Storage: both are S3-API-compatible object storage with
     lifecycle policies")
   - cite only from the evidence actually retrieved — never invent a citation
   - report a confidence score
   Wrap the requirement/evidence text through `wrap_untrusted()` per the
   existing injection-containment pattern (documents/injection.py), same as
   `understanding.py` and `search_tools.py` already do.
   On call failure, invalid output, or exhausted token budget: fall back to
   the current deterministic `_draft_one` logic exactly as it exists today —
   this must never hard-fail an RFP run.

3. Update `rfp.gate` (human_gate) to also flag for review any answer where the
   LLM used a semantic_match signal (not an exact token match) — a cross-vendor
   equivalence claim in a bid response should always get a human's eyes before
   `rfp.export`, regardless of the model's reported confidence. Keep the
   existing confidence<0.85 / unmet_prerequisites flags as additional triggers,
   not a replacement.

4. Tests: unit-test the embedding-similarity ranking with a small fixture
   catalog (include an "Azure-Blob-Storage-named requirement / OBS-named
   product" case as a regression test for the exact scenario this was built
   for). Use the existing fake LLM/embedding provider pattern (see
   embeddings/fake.py) to test the new `_draft_one` deterministically —
   both the happy path and the fallback-on-failure path.

============================================================
GOAL 3 — Freshness monitoring: crawl the whole site, ingest as real data
============================================================

Current state: `freshness/scraper.py::check_source()` fetches one URL, hashes
it, and discards the body — it only ever proves "did this one page change,"
nothing is persisted as searchable content.

Changes:

1. Add a crawl step: given a `VendorSource` seed URL, discover other publicly
   reachable pages under the same origin (parse `<a href>` from fetched HTML,
   normalize and dedupe URLs, restrict to same-origin or an explicitly
   configured path prefix). Every discovered URL — not just the seed — MUST
   be re-validated through `net/ssrf.py::validate_url()`/`fetch()` before
   being requested; do not bypass the SSRF gate for crawl-discovered links.

2. Respect crawl scope and politeness limits, all configurable via
   app.core.config.settings (mirror the existing `freshness_max_bytes` /
   `freshness_default_interval_seconds` pattern):
   - check and respect robots.txt for the origin before crawling it at all
     (this doesn't exist anywhere in net/ssrf.py today — add it)
   - max pages per crawl run, max depth
   - a delay between requests (don't hammer the vendor's site)
   - run the crawl as a background job (jobs/queue.py), never inline in an
     API request

3. For each fetched page, extract structured content using the existing
   `_extract_html()` in documents/extraction.py (already strips script/style
   and tracks heading hierarchy — do not write a second HTML parser). Feed the
   resulting bytes through the standard ingestion path: `create_document()` +
   `enqueue_ingestion()`, exactly like Goal 1's RFP indexing — this is what
   makes the crawl genuinely become part of the searchable KB (chunked,
   embedded, understood) rather than just a hash. Do not hand-roll a
   markdown/JSON writer — `create_document` + the existing pipeline already
   produces citable, chunked, embedded content; converting to markdown
   yourself first would just be thrown away at the chunking step.

4. Add a link from VendorSource to the Document(s) it produces (new FK/table
   — one source can now back many pages, so likely a new join table
   VendorSourcePage{vendor_source_id, url, document_id, last_hash} rather than
   a single FK on VendorSource). On re-crawl, a changed page should supersede
   its previous Document version (reuse `find_previous_version` /
   `supersedes_id` — this already exists in create_document, just make sure
   filenames are stable per-URL so version-matching works), and a page that
   disappeared from the site should have its Document's `is_current` flipped
   off rather than left indexed forever.

5. Keep the existing single-URL hash-diff logic as the trigger for whether a
   given page gets re-ingested — don't re-embed unchanged pages on every
   crawl, only changed/new ones. The crawl-discovery step itself (finding
   what pages exist) still needs to run each check to catch new/removed pages.

6. FreshnessAlert should reference which page(s) changed post-crawl, not just
   "the source changed" — useful since a source can now represent dozens of
   pages.

7. Decide and implement the approval_state for scraped Documents explicitly:
   RetrievalFilters uses `approved_only=True` for citations elsewhere in the
   system (see hybrid_search_tool). Either auto-approve scraped vendor pages
   (since these are sources you deliberately chose to monitor) or route them
   through the same review queue as manual uploads — pick one and make it a
   setting, don't leave it implicit.

8. Tests: mock the fetcher to return a small fake site (3-4 linked pages, one
   off-origin link that must be rejected, one link that should hit the SSRF
   block). Assert: crawl stays in scope, off-origin/blocked links are never
   fetched, robots.txt disallow is respected, re-crawl of an unchanged page
   doesn't create a duplicate Document, and a changed page supersedes the old
   version.

============================================================
THINGS YOU DIDN'T ASK FOR BUT SHOULD DECIDE ON
============================================================

- Cost ceiling on the crawl: a "scrape everything publicly available" job on
  a large vendor site can be hundreds of pages × embeddings. Add a hard
  max-pages-per-run setting with a sane default (e.g. 50) so a single
  misconfigured source can't blow the monthly token/embedding budget.
- pgvector indexing: security-and-scalability.md already calls for HNSW/IVFFlat
  indexing at scale — if freshness crawling meaningfully grows chunk volume,
  confirm the current index is tuned for it, not just correctness-tested on a
  small fixture.
- Audit trail: since RFP responses are contractual/bid documents, log which
  requirements were resolved via semantic (non-exact) matching in the
  exported artifact itself (an appendix row: "AI-inferred equivalence,
  human-reviewed") so there's a paper trail on any cross-vendor claim that
  ends up in a client-facing document.
- Legal/ToS: robots.txt compliance is a floor, not a guarantee a vendor's ToS
  permits bulk scraping of their site — that's a policy decision for you, not
  something to silently assume away in code.