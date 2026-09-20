# Graph Report - personal-knowledge-ai  (2026-09-20)

## Corpus Check
- 144 files · ~55,599 words
- Verdict: corpus is large enough that graph structure adds value.
- Unclassified: 6 file(s) not represented in the graph (top: (none) 3, .example 2, .css 1)

## Summary
- 1379 nodes · 3254 edges · 115 communities (66 shown, 49 thin omitted)
- Extraction: 90% EXTRACTED · 10% INFERRED · 0% AMBIGUOUS · INFERRED: 325 edges (avg confidence: 0.95)
- Token cost: 0 input · 0 output

## Graph Freshness
- Built from commit: `b2be70ba`
- Run `git rev-parse HEAD` and compare to check if the graph is stale.
- Run `graphify update .` after code changes (no API cost).

## Community Hubs (Navigation)
- documents/service.py
- extraction.py
- StorageError
- package.json
- ssrf.py
- Personal Knowledge AI Workspace
- ProviderRateLimited
- Project Plan: Solution Engineering Knowledge Workspace
- Settings
- compilerOptions
- test_generation.py
- vercel.json
- test_permissions.py
- DocumentMetadataIn
- RetrievalFilters
- models.py
- Roadmap: Notes + Grounded AI
- Evaluation Strategy (Phase 4)
- Graphify Knowledge Graph Rules
- workflows/graphify.md
- verify_project.py
- Graphify Synchronization and Knowledge Graph Navigation
- 2. Verification Runbook
- Workspace Rules - Personal Knowledge AI
- retrieval/search.py
- Code Modification & Feature Verification Rules
- index.ts
- jobs/worker.py
- extract
- app_documents_scanning
- app_documents_limits
- generation/service.py
- PredicateSet
- App.tsx
- Deadline
- app_retrieval_spec
- bulk_load_test.py
- queue.py
- pytest
- run_eval.py
- test_safety_limits.py
- test_integration.py
- job_stats
- DocumentList.tsx
- app_api_routes
- app_core_logging
- documents.py
- errors.py
- reciprocal_rank_fusion
- labels.py
- test_injection.py
- GroundedChat
- AppError
- test_search_sql.py
- app_core_config
- org_id
- app_documents
- _HtmlTextExtractor
- Block
- app_core_errors
- app_db_migrations
- app_db_models
- fixtures.py
- app_db_session
- app_documents_chunking
- app_documents_extraction
- app_documents_anchors
- Phase 1 and Phase 2, as built
- What is left
- app_documents_injection
- app_documents_metadata
- app_retrieval_fusion
- Roadmap: Notes + Grounded AI
- app_documents_schemas
- app_documents_service
- app_ocr_base
- app_documents_sniffing
- app_jobs
- app_jobs_worker
- scanning.py
- app_net_ssrf
- ask.py
- devDependencies
- GeminiLLMProvider
- app_retrieval_permissions
- app_retrieval_schemas
- app_retrieval_search
- routes/search.py
- app_retrieval_sql
- app_security_deps
- app_security_labels
- app_security_principal
- chunking.py
- app_jobs_backoff
- personal-knowledge-ai-backend
- OcrProvider
- tests
- 5. Phase 2: hybrid retrieval
- tempfile
- config.py
- test_jobs.py
- Phase 3 Grounded Generation Baseline
- Phase 3: Grounded Answers, as built

## God Nodes (most connected - your core abstractions)
1. `Principal` - 54 edges
2. `Document` - 37 edges
3. `DocumentMetadataIn` - 37 edges
4. `extract()` - 32 edges
5. `RetrievalFilters` - 32 edges
6. `search()` - 30 edges
7. `create_document()` - 27 edges
8. `restricted_principal()` - 27 edges
9. `Sensitivity` - 26 edges
10. `owner_principal()` - 25 edges

## Surprising Connections (you probably didn't know these)
- `3. Intentional Changes & Design Decisions` --references--> `AskIn`  [INFERRED]
  docs/PHASE3.md → backend/app/generation/schemas.py
- `1. Security First Principles` --references--> `Settings`  [INFERRED]
  .agents/rules/security-and-scalability.md → backend/app/core/config.py
- `C. Secrets & Environment Isolation` --references--> `Settings`  [INFERRED]
  .agents/skills/security-and-scalability/SKILL.md → backend/app/core/config.py
- `Deliberate decisions` --references--> `ProviderRateLimited`  [INFERRED]
  docs/architecture.md → backend/app/core/errors.py
- `7. What Phase 3 inherits` --references--> `wrap_untrusted()`  [EXTRACTED]
  docs/PHASE1-2.md → backend/app/documents/injection.py

## Import Cycles
- None detected.

## Communities (115 total, 49 thin omitted)

### Community 0 - "documents/service.py"
Cohesion: 0.18
Nodes (24): Document, DocumentStatus, content_hash(), create_document(), delete_document(), enqueue_ingestion(), find_duplicate(), find_previous_version() (+16 more)

### Community 1 - "extraction.py"
Cohesion: 0.20
Nodes (22): ExtractionError, _decode(), _docx_heading_level(), _extract_docx(), _extract_html(), _extract_pdf(), _extract_pptx(), _extract_text() (+14 more)

### Community 2 - "StorageError"
Cohesion: 0.12
Nodes (11): StorageError, ObjectStorage, ABC, Original uploaded files live here. PostgreSQL only stores the key., LocalStorage, Path, Development-only stand-in for R2. Never use on Render (ephemeral filesystem)., R2Storage (+3 more)

### Community 3 - "package.json"
Cohesion: 0.11
Nodes (17): dependencies, react, react-dom, name, private, scripts, build, dev (+9 more)

### Community 4 - "ssrf.py"
Cohesion: 0.12
Nodes (29): A URL resolved to an address the fetcher refuses to touch., SsrfBlocked, classify_host(), fetch(), FetchedResource, is_blocked_address(), SSRF-safe URL fetching. Project_Plan.md Phase 1: "URL ingestion through an…, Return the denial reasons for a host. Empty list means allowed. Addresses may… (+21 more)

### Community 5 - "Personal Knowledge AI Workspace"
Cohesion: 0.10
Nodes (18): Deploy, Design rules this repo actually follows, Ingest a file without the UI, Personal Knowledge AI Workspace, Repository layout, Run it locally, Stack, Tests (+10 more)

### Community 6 - "ProviderRateLimited"
Cohesion: 0.25
Nodes (7): ProviderRateLimited, Provider returned 429. Tracked separately from retrieval failures., Deliberate decisions, Ingestion pipeline, Not built yet (on purpose), Request paths implemented in Phase 1, V1 Architecture (as built)

### Community 7 - "Project Plan: Solution Engineering Knowledge Workspace"
Cohesion: 0.09
Nodes (21): 0. Decided parameters, 1. What this is, 2. What the size of this changes, 3. Core principles, 4. Phase map, 5. Testing strategy (all phases), 6. Security posture, 7. Scalability posture (+13 more)

### Community 8 - "Settings"
Cohesion: 0.07
Nodes (20): 1. Security First Principles, 2. Scalability & High-Performance Engineering, Security & Scalability Architecture Rules, 1. Security Engineering & Auditing, 2. Scalability & High-Performance Engineering, 3. Architecture Review Checklist, A. Authentication & Authorization, A. High-Scale Vector Search (`pgvector`) (+12 more)

### Community 9 - "compilerOptions"
Cohesion: 0.14
Nodes (13): compilerOptions, isolatedModules, jsx, lib, module, moduleResolution, noEmit, resolveJsonModule (+5 more)

### Community 10 - "test_generation.py"
Cohesion: 0.09
Nodes (32): _build_retrieval_filters(), Convert the generation request filters to retrieval filters., GroundedAnswer, GroundedAnswerChunk, LLMProvider, ABC, LLM provider interface. Phase 3 deliverable. The RAG layer never imports a…, One piece of a streaming response. (+24 more)

### Community 11 - "vercel.json"
Cohesion: 0.40
Nodes (4): buildCommand, installCommand, outputDirectory, $schema

### Community 12 - "test_permissions.py"
Cohesion: 0.16
Nodes (25): build_predicate_set(), predicates_for(), Assemble the full candidate predicate set: permissions, corpus, then filters., owner_principal(), The single collateral owner. Full read access by decision, not by accident., fields(), Permission-aware retrieval. Project_Plan.md Phase 2 exit criterion: "permission…, Project_Plan.md section 0 decides collateral has a single owner. That is a… (+17 more)

### Community 13 - "DocumentMetadataIn"
Cohesion: 0.11
Nodes (20): DocumentMetadataIn, BaseModel, field_validator, Why this document may not be marked `approved` yet., Metadata accepted on upload. Every field optional, every default safe., normalize(), Parse an incoming label, falling back to `default` when one is provided.…, parametrize (+12 more)

### Community 22 - "RetrievalFilters"
Cohesion: 0.17
Nodes (23): corpus_predicates(), Op, Origin, StrEnum, Retrieval filters, expressed as data. Why an intermediate representation…, Structural predicates. A superseded version or a half-ingested document is…, Caller-supplied narrowing. Every field is optional; none of them can widen what…, RetrievalFilters (+15 more)

### Community 23 - "models.py"
Cohesion: 0.19
Nodes (15): AccessGrant, Per-account read grant. Consumed by retrieval today, issued by an admin UI in…, get_db(), Session, _parse_uuid(), Session, UUID, FastAPI dependency that turns a request into a `Principal`. Isolated from… (+7 more)

### Community 24 - "Roadmap: Notes + Grounded AI"
Cohesion: 0.15
Nodes (12): Design rules, Feature parity map, Open decisions, Phase 10: Platform and ecosystem, Phase 6: Notes core, Phase 7: Linking and graph, Phase 8: Notebook studio, Phase 9: Differentiators (+4 more)

### Community 25 - "Evaluation Strategy (Phase 4)"
Cohesion: 0.40
Nodes (4): Evaluation Strategy (Phase 4), Experiments, Labeled set, Metrics

### Community 26 - "Graphify Knowledge Graph Rules"
Cohesion: 0.50
Nodes (3): 1. Prompt-Level Graphify Trigger (Every Prompt), 2. Automatic Graph Synchronization (Every Codebase Change), Graphify Knowledge Graph Rules

### Community 29 - "verify_project.py"
Cohesion: 0.25
Nodes (13): py_compile, main(), Graphify automatic update script. Re-extracts AST nodes and edges across code…, run_update(), main(), print_section(), Path, Project Test & Verification Runner. Executes verification steps across backend… (+5 more)

### Community 30 - "Graphify Synchronization and Knowledge Graph Navigation"
Cohesion: 0.18
Nodes (10): 1. When to Use, 2. Navigating the Graph (Prompt Trigger), 3. Automatic & Manual Graph Synchronization, 4. Validation, A. Semantic Subgraph Query, B. Shortest Dependency Path, C. Node Explanation, Graphify Synchronization and Knowledge Graph Navigation (+2 more)

### Community 31 - "2. Verification Runbook"
Cohesion: 0.22
Nodes (8): 1. When to Use, 2. Verification Runbook, 3. Verification Checklist Before Concluding, Step 1: Run Unified Project Verification, Step 2: Backend Unit & Integration Tests, Step 3: Frontend Typechecking and Production Build, Step 4: Adding Tests for New Features, Test and Verification Skill

### Community 32 - "Workspace Rules - Personal Knowledge AI"
Cohesion: 0.18
Nodes (8): 1. Graphify Knowledge Graph (Active & Enforced), 2. Test & Verification Guarantee, 3. Security & Scalability Priorities, Workspace Rules - Personal Knowledge AI, 1. Graphify Knowledge Graph (Active & Enforced), 2. Test & Verification Guarantee, 3. Security & Scalability Priorities, Workspace Rules - Personal Knowledge AI

### Community 33 - "retrieval/search.py"
Cohesion: 0.12
Nodes (19): get_logger(), _hydrate(), _ms(), permission_predicate_count(), Session, Hybrid retrieval: pgvector + PostgreSQL full-text search, fused with RRF. Shape…, Used by the regression test that guards the Phase 2 exit criterion., search() (+11 more)

### Community 35 - "index.ts"
Cohesion: 0.19
Nodes (15): ChunkInspector(), Props, api, AskResponse, BulkUploadOut, Conversation, ConversationListResponse, DocumentChunk (+7 more)

### Community 36 - "jobs/worker.py"
Cohesion: 0.16
Nodes (14): setup_logging(), loop(), The single ingestion worker. Runs either inside the API process (a daemon…, start_background_workers(), stop_background_workers(), worker_id(), lifespan(), get (+6 more)

### Community 37 - "extract"
Cohesion: 0.15
Nodes (20): detect_file_type(), extract(), Path, Extract from raw bytes or a path. Bytes are preferred; paths are a convenience., Extension-based type, kept for scripts and tests. The upload path uses…, parametrize, Golden extraction tests: one fixture per format, plus one malformed file per…, Every failure must be a named application error with a readable message, never… (+12 more)

### Community 40 - "generation/service.py"
Cohesion: 0.06
Nodes (71): Base, Conversation, Message, SchemaMigration, Workspace, add_message(), auto_title(), create_conversation() (+63 more)

### Community 41 - "PredicateSet"
Cohesion: 0.15
Nodes (9): PermissionFilterMissing, A retrieval query was assembled without its permission predicates. This is a…, assert_enforced(), Permission-aware retrieval. Project_Plan.md Phase 2: "candidates are filtered…, Predicate, PredicateSet, The tripwire. An empty or filter-only predicate set must never run., test_removing_the_permission_predicates_fails_loudly() (+1 more)

### Community 42 - "App.tsx"
Cohesion: 0.24
Nodes (7): App(), SearchExplorer(), Props, UploadButton(), useDocuments(), frontend_src_index, react

### Community 43 - "Deadline"
Cohesion: 0.20
Nodes (6): ExtractionTimeout, Parsing exceeded its wall-clock budget. Tracked separately: it usually means a…, Deadline, Cooperative wall-clock budget. Extraction loops call `check()` per page., test_deadline_does_not_fire_early(), test_deadline_expires_and_names_what_timed_out()

### Community 45 - "bulk_load_test.py"
Cohesion: 0.18
Nodes (10): argparse, os, resource, Bulk ingestion test at 10x the real corpus. cd backend &&…, rss_mb(), synthetic_markdown(), load_dataset(), Path (+2 more)

### Community 46 - "queue.py"
Cohesion: 0.22
Nodes (20): IngestionJob, JobStatus, Durable ingestion queue. Deviation from the plan, on purpose: FastAPI…, claim(), enqueue(), fail(), _now(), Session (+12 more)

### Community 47 - "pytest"
Cohesion: 0.27
Nodes (8): applied_migrations(), Apply every unapplied step. Returns the names that ran., run_migrations(), database(), _database_reachable(), Test configuration. Two rules this file exists to enforce: * No test may make a…, Engine, pytest

### Community 48 - "run_eval.py"
Cohesion: 0.12
Nodes (18): EvaluationQuestion, json, pathlib, get_graph_stats(), main(), Path, Graphify PreInvocation hook script. Executed by Antigravity prior to model…, Ingest local files through the real pipeline without going through HTTP. cd… (+10 more)

### Community 49 - "test_safety_limits.py"
Cohesion: 0.17
Nodes (24): The file tripped a pre-parse safety limit (zip bomb, entity expansion,…, UnsafeFile, ArchiveReport, check_html_safety(), guard_extracted_size(), inspect_ooxml(), ParseLimits, Pre-parse safety limits. Project_Plan.md asks for "parsing in a resource-… (+16 more)

### Community 50 - "test_integration.py"
Cohesion: 0.16
Nodes (21): DocumentChunk, Organization, Tenant root. Phase 0 will add row-level security keyed on this column; the…, process_document(), Run extraction through persistence. Owns its own session: the worker calls it., ingest(), org(), owner() (+13 more)

### Community 51 - "job_stats"
Cohesion: 0.32
Nodes (8): job_stats(), JobOut, list_jobs(), BaseModel, get, Session, QueueStatsOut, Per-job status. Every failure is individually explainable and retryable, which…

### Community 52 - "DocumentList.tsx"
Cohesion: 0.38
Nodes (4): DocumentList(), formatSize(), Props, KnowledgeDocument

### Community 55 - "documents.py"
Cohesion: 0.16
Nodes (29): delete_document(), document_chunks(), document_status(), get_document(), list_documents(), patch_metadata(), delete, get (+21 more)

### Community 56 - "errors.py"
Cohesion: 0.11
Nodes (35): GenerationRateLimited, GenerationRefused, PermissionDenied, The caller's grants do not cover the resource. Surfaced as 404, never 403, so…, The organization's token budget for this period has been reached., The user has exceeded their per-minute generation rate limit., The model refused to answer because context was insufficient. This is not an…, TokenBudgetExhausted (+27 more)

### Community 57 - "reciprocal_rank_fusion"
Cohesion: 0.18
Nodes (19): FusedHit, RankedList, Reciprocal Rank Fusion. Pure, deterministic, and unit-tested without a…, One retrieval branch's output, best first., 1-based rank per id, first occurrence wins., Fuse ranked lists. `score = sum(weight / (k + rank))` over the branches. Ties…, reciprocal_rank_fusion(), branches() (+11 more)

### Community 58 - "labels.py"
Cohesion: 0.26
Nodes (9): Collateral metadata captured at ingest. **Deliberate deviation from…, ApprovalState, Ownership, StrEnum, The controlled vocabularies Project_Plan.md treats as first-class. Kept in one…, Every ladder label a principal with `maximum` may read., Role, sensitivities_up_to() (+1 more)

### Community 59 - "test_injection.py"
Cohesion: 0.09
Nodes (29): InjectionFinding, neutralize_fences(), Prompt-injection containment. Project_Plan.md principle 7: "Ingested content is…, Strip forged delimiters so document text cannot close its own fence. This is…, Fence retrieved content for a prompt. Phase 3 must use this for every source., Flag instruction-like passages. Never blocks ingestion., scan_for_injection(), wrap_untrusted() (+21 more)

### Community 60 - "GroundedChat"
Cohesion: 0.48
Nodes (6): GroundedChat(), handleDelete(), handleSend(), loadConversationDetails(), loadConversations(), loadConversationSources()

### Community 61 - "AppError"
Cohesion: 0.13
Nodes (18): _as_http(), _filename_for_url(), ingest_paste(), ingest_url(), _metadata_from_form(), Exception, post, Bulk upload. Many files at once, or a whole folder drop from the browser. One… (+10 more)

### Community 62 - "test_search_sql.py"
Cohesion: 0.12
Nodes (32): _coerce(), compile_predicate(), compile_predicate_set(), Exception, Translate the predicate IR into SQLAlchemy clauses. Thin on purpose. All of the…, AND everything together. The origin of a predicate never affects how it is…, UnknownFilterField, Sensitivity (+24 more)

### Community 64 - "org_id"
Cohesion: 0.33
Nodes (6): event_generator(), db(), org_id(), fixture, 1. The dependency the plan creates and this build had to resolve, Phase 0: Foundation and security baseline

### Community 66 - "_HtmlTextExtractor"
Cohesion: 0.18
Nodes (5): _HeadingTracker, _HtmlTextExtractor, Stdlib parser: tolerant, and it never resolves external entities or DTDs., Maintains the current heading path, e.g. ('Licensing', 'Enterprise tier')., HTMLParser

### Community 67 - "Block"
Cohesion: 0.27
Nodes (16): chunk_blocks(), Block, A structural unit of source text (a page, slide, sheet range, or section)., Chunking. Determinism first: the Phase 2 baseline is only comparable if…, The old grouping key was (page, section), which collapsed every heading-path…, `overlap = chunk_overlap or settings.chunk_overlap` silently turned an explicit…, test_anchor_label_is_human_readable(), test_chunk_indexes_are_sequential_and_deterministic() (+8 more)

### Community 71 - "fixtures.py"
Cohesion: 0.08
Nodes (28): UnsupportedFileType, decide_file_type(), normalize_extension(), Decide what a file actually is from its bytes, not from its name.…, Content wins. The declared extension is recorded, never trusted. Raises…, Best-effort content identification of an in-memory upload., sniff(), _sniff_zip() (+20 more)

### Community 76 - "Phase 1 and Phase 2, as built"
Cohesion: 0.25
Nodes (7): 2. Phase 1: ingestion, 3. Deviation: metadata is not all mandatory at upload, 4. Honest gaps, 6. Running it, 7. What Phase 3 inherits, Changes made on purpose, Phase 1 and Phase 2, as built

### Community 77 - "What is left"
Cohesion: 0.14
Nodes (13): Also included (small, load-bearing extras), Build Status, Known deviations from the plan document, Phase 0 - Project setup, Phase 1 - Document ingestion, Phase 2 - Retrieval (not started), Phase 3 - Grounded generation (not started), Phase 4 - Evaluation (not started) (+5 more)

### Community 81 - "Roadmap: Notes + Grounded AI"
Cohesion: 0.15
Nodes (12): Design rules, Feature parity map, Open decisions, Phase 10: Platform and ecosystem, Phase 6: Notes core, Phase 7: Linking and graph, Phase 8: Notebook studio, Phase 9: Differentiators (+4 more)

### Community 88 - "scanning.py"
Cohesion: 0.10
Nodes (20): MalwareDetected, A malware scanner is configured but unreachable. Uploads fail closed., ScannerUnavailable, ClamAvScanner, get_scanner(), HeuristicScanner, NullScanner, ABC (+12 more)

### Community 90 - "ask.py"
Cohesion: 0.08
Nodes (48): ask_endpoint(), ask_in_conversation_endpoint(), _conv_to_out(), create_conversation_endpoint(), delete_conversation_endpoint(), get_conversation_endpoint(), get_conversation_sources_endpoint(), list_conversations_endpoint() (+40 more)

### Community 91 - "devDependencies"
Cohesion: 0.33
Nodes (6): devDependencies, @types/react, @types/react-dom, typescript, vite, @vitejs/plugin-react

### Community 92 - "GeminiLLMProvider"
Cohesion: 0.15
Nodes (12): ProviderError, External inference provider failed (network, 5xx, bad payload)., _detect_refusal(), _extract_cited_indices(), GeminiLLMProvider, _map_citations(), retry, Detect whether the model refused to answer due to insufficient context. (+4 more)

### Community 96 - "routes/search.py"
Cohesion: 0.24
Nodes (11): post, Session, Hybrid retrieval with its scores and fusion inputs exposed. This is the Phase 2…, search_endpoint(), BaseModel, The debug endpoint's contract: scores and fusion inputs are always exposed.…, Caller-supplied narrowing. Required, not optional, per Phase 2: every field…, SearchFiltersIn (+3 more)

### Community 101 - "chunking.py"
Cohesion: 0.12
Nodes (8): Anchor, Citation anchors. A citation is only trustworthy if it resolves to one place in…, Grouping key for chunking: a chunk never spans two anchors., Human-readable citation suffix, e.g. 'p. 12' or 'Pricing!A1:D20'., Chunk, Deterministic, structure-aware chunking. Rules kept intentionally simple until…, _windows(), itertools

### Community 104 - "OcrProvider"
Cohesion: 0.16
Nodes (9): OcrProvider, ABC, Optical character recognition for PDFs with no text layer., get_ocr_provider(), NullOcrProvider, The default. OCR is off unless someone deliberately turns it on. Reasoning…, pytesseract + Pillow. Optional import: the API starts fine without either., TesseractOcrProvider (+1 more)

### Community 106 - "5. Phase 2: hybrid retrieval"
Cohesion: 0.50
Nodes (4): 5. Phase 2: hybrid retrieval, How "filters before fusion" is guaranteed, Known performance trade-off, What is not done, and should not be faked

### Community 130 - "config.py"
Cohesion: 0.20
Nodes (8): dependencies(), health(), get, Can the backend reach PostgreSQL, pgvector, object storage, and the embedding…, Idempotent, recorded schema migrations. The project had none:…, pydantic, pydantic_settings, sqlalchemy_engine

### Community 132 - "test_jobs.py"
Cohesion: 0.07
Nodes (23): EmbeddingProvider, ABC, Embed chunk text for indexing., Embed a user question for retrieval., The RAG layer talks to this, never to a vendor SDK directly., get_embedding_provider(), FakeEmbeddingProvider, Deterministic hash-based vectors. For tests and offline development only. (+15 more)

### Community 141 - "Phase 3 Grounded Generation Baseline"
Cohesion: 0.40
Nodes (4): Adversarial Test Cases, Benchmark Summary, Phase 3 Grounded Generation Baseline, Refusal Test Cases

### Community 142 - "Phase 3: Grounded Answers, as built"
Cohesion: 0.25
Nodes (7): 1. Overview of Phase 3 Deliverables, 2. Architectural Components, 3. Intentional Changes & Design Decisions, 4. Honest Gaps & Future Work, A. LLM Provider Layer (`app/llm/`), C. API Endpoints (`app/api/routes/ask.py`), Phase 3: Grounded Answers, as built

## Knowledge Gaps
- **154 isolated node(s):** `personal-knowledge-ai-backend`, `name`, `private`, `version`, `type` (+149 more)
  These have ≤1 connection - possible missing edges or undocumented components. (Counts symbols only; 589 node(s) total have ≤1 connection when file, concept and rationale nodes are included.)
- **49 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `Principal` connect `documents.py` to `routes/search.py`, `documents/service.py`, `retrieval/search.py`, `org_id`, `labels.py`, `generation/service.py`, `PredicateSet`, `test_permissions.py`, `job_stats`, `models.py`, `ask.py`, `AppError`, `test_search_sql.py`?**
  _High betweenness centrality (0.065) - this node is a cross-community bridge._
- **Why does `Settings` connect `Settings` to `config.py`?**
  _High betweenness centrality (0.041) - this node is a cross-community bridge._
- **Why does `Document` connect `documents/service.py` to `retrieval/search.py`, `generation/service.py`, `What is left`, `run_eval.py`, `test_integration.py`, `documents.py`, `models.py`, `labels.py`, `AppError`, `test_search_sql.py`?**
  _High betweenness centrality (0.030) - this node is a cross-community bridge._
- **Are the 35 inferred relationships involving `Principal` (e.g. with `ask_endpoint()` and `ask_in_conversation_endpoint()`) actually correct?**
  _`Principal` has 35 INFERRED edges - model-reasoned connections that need verification._
- **Are the 27 inferred relationships involving `Document` (e.g. with `get_document()` and `ingest_paste()`) actually correct?**
  _`Document` has 27 INFERRED edges - model-reasoned connections that need verification._
- **Are the 10 inferred relationships involving `DocumentMetadataIn` (e.g. with `ingest_paste()` and `ingest_url()`) actually correct?**
  _`DocumentMetadataIn` has 10 INFERRED edges - model-reasoned connections that need verification._
- **Are the 6 inferred relationships involving `extract()` (e.g. with `_extract_docx()` and `_extract_html()`) actually correct?**
  _`extract()` has 6 INFERRED edges - model-reasoned connections that need verification._