# Graph Report - personal-knowledge-ai  (2026-09-20)

## Corpus Check
- 221 files · ~82,279 words
- Verdict: corpus is large enough that graph structure adds value.
- Unclassified: 6 file(s) not represented in the graph (top: .example 3, (none) 2, .css 1)

## Summary
- 2099 nodes · 5299 edges · 143 communities (105 shown, 38 thin omitted)
- Extraction: 88% EXTRACTED · 12% INFERRED · 0% AMBIGUOUS · INFERRED: 636 edges (avg confidence: 0.94)
- Token cost: 0 input · 0 output

## Graph Freshness
- Built from commit: `d59756cd`
- Run `git rev-parse HEAD` and compare to check if the graph is stale.
- Run `graphify update .` after code changes (no API cost).

## Community Hubs (Navigation)
- Document
- backend/app/documents/extraction.py
- StorageError
- package.json
- SsrfBlocked
- Personal Knowledge AI Workspace
- V1 Architecture (as built)
- Project Plan: Solution Engineering Knowledge Workspace
- 1. Security Engineering & Auditing
- compilerOptions
- test_generation.py
- vercel.json
- graphify_preinvocation.py
- DocumentMetadataIn
- repo/backend/tests/test_permissions.py
- Roadmap: Notes + Grounded AI
- Evaluation Strategy (Phase 4)
- Graphify Knowledge Graph Rules
- workflows/graphify.md
- verify_project.py
- Graphify Synchronization and Knowledge Graph Navigation
- 2. Verification Runbook
- Workspace Rules - Personal Knowledge AI
- Workspace Rules - Personal Knowledge AI
- Code Modification & Feature Verification Rules
- EmbeddingProvider
- backend/app/jobs/worker.py
- UnsupportedFileType
- repo/backend/tests/test_scanning.py
- repo/backend/tests/test_safety_limits.py
- generation/service.py
- backend/tests/test_permissions.py
- test_generation_prompts.py
- backend/app/api/routes/documents.py
- backend/tests/test_search_sql.py
- repo/backend/tests/test_search_sql.py
- IngestionJob
- repo/backend/app/documents/service.py
- app_core_config
- UnsafeFile
- backend/tests/test_integration.py
- repo/backend/tests/test_sniffing.py
- repo/backend/app/documents/extraction.py
- Principal
- app_core_logging
- _scoped
- test_rate_limit.py
- reciprocal_rank_fusion
- Sensitivity
- backend/tests/test_injection.py
- repo/backend/tests/test_injection.py
- DuplicateDocument
- RetrievalFilters
- extract
- backend/app/db/models.py
- repo/backend/app/api/routes/documents.py
- _HtmlTextExtractor
- Block
- RetrievalFilters
- Block
- PredicateSet
- backend/tests/fixtures.py
- pytest
- repo/backend/tests/fixtures.py
- backend/app/documents/sniffing.py
- dataclasses
- Phase 1 and Phase 2, as built
- What is left
- AppError
- Phase 1 and Phase 2, as built
- repo/backend/app/retrieval/search.py
- Roadmap: Notes + Grounded AI
- get_ocr_provider
- search_endpoint
- io
- repo/backend/app/db/models.py
- repo/backend/app/documents/scanning.py
- repo/backend/tests/test_integration.py
- backend/app/documents/scanning.py
- Settings
- ask.py
- Settings
- llm/gemini.py
- OcrProvider
- Build Status
- repo/backend/tests/test_jobs.py
- backend/app/retrieval/schemas.py
- repo/backend/app/jobs/queue.py
- backend/tests/conftest.py
- Sensitivity
- repo/backend/app/retrieval/schemas.py
- Anchor
- backend/tests/test_jobs.py
- owner_principal
- TesseractOcrProvider
- Security & Scalability Architecture Rules
- personal-knowledge-ai-backend
- personal-knowledge-ai-backend
- tempfile
- get_embedding_provider
- backend/tests/test_scanning.py
- GeminiEmbeddingProvider
- repo/backend/app/jobs/worker.py
- job_stats
- FakeEmbeddingProvider
- job_stats
- HeuristicScanner
- Chunk
- run_generation_eval.py
- search_endpoint
- Phase 3 Grounded Generation Baseline
- Phase 3: Grounded Answers, as built

## God Nodes (most connected - your core abstractions)
1. `Principal` - 74 edges
2. `Document` - 60 edges
3. `DocumentMetadataIn` - 54 edges
4. `RetrievalFilters` - 49 edges
5. `Sensitivity` - 41 edges
6. `UnsafeFile` - 38 edges
7. `Block` - 35 edges
8. `DocumentMetadataIn` - 34 edges
9. `extract()` - 32 edges
10. `extract()` - 31 edges

## Surprising Connections (you probably didn't know these)
- `3. Intentional Changes & Design Decisions` --references--> `AskIn`  [INFERRED]
  docs/PHASE3.md → backend/app/generation/schemas.py
- `1. Overview of Phase 3 Deliverables` --references--> `SourceMetadata`  [INFERRED]
  docs/PHASE3.md → backend/app/llm/base.py
- `B. Generation & RAG Orchestration (`app/generation/`)` --references--> `check_rate_limit()`  [INFERRED]
  docs/PHASE3.md → backend/app/generation/rate_limit.py
- `B. Generation & RAG Orchestration (`app/generation/`)` --references--> `check_token_budget()`  [INFERRED]
  docs/PHASE3.md → backend/app/generation/rate_limit.py
- `B. Generation & RAG Orchestration (`app/generation/`)` --references--> `record_token_usage()`  [INFERRED]
  docs/PHASE3.md → backend/app/generation/rate_limit.py

## Import Cycles
- None detected.

## Communities (143 total, 38 thin omitted)

### Community 0 - "Document"
Cohesion: 0.18
Nodes (25): set_approval(), AppError, Exception, Base application error., Document, content_hash(), create_document(), delete_document() (+17 more)

### Community 1 - "backend/app/documents/extraction.py"
Cohesion: 0.12
Nodes (36): ExtractionError, _decode(), _docx_heading_level(), extract(), _extract_docx(), _extract_html(), _extract_pdf(), _extract_pptx() (+28 more)

### Community 2 - "StorageError"
Cohesion: 0.12
Nodes (11): StorageError, ObjectStorage, ABC, Original uploaded files live here. PostgreSQL only stores the key., LocalStorage, Path, Development-only stand-in for R2. Never use on Render (ephemeral filesystem)., R2Storage (+3 more)

### Community 3 - "package.json"
Cohesion: 0.06
Nodes (38): dependencies, react, react-dom, devDependencies, @types/react, @types/react-dom, typescript, vite (+30 more)

### Community 4 - "SsrfBlocked"
Cohesion: 0.06
Nodes (56): app_net_ssrf, A URL resolved to an address the fetcher refuses to touch., SsrfBlocked, classify_host(), fetch(), FetchedResource, is_blocked_address(), SSRF-safe URL fetching. Project_Plan.md Phase 1: "URL ingestion through an… (+48 more)

### Community 5 - "Personal Knowledge AI Workspace"
Cohesion: 0.10
Nodes (18): Deploy, Design rules this repo actually follows, Ingest a file without the UI, Personal Knowledge AI Workspace, Repository layout, Run it locally, Stack, Tests (+10 more)

### Community 6 - "V1 Architecture (as built)"
Cohesion: 0.33
Nodes (5): Deliberate decisions, Ingestion pipeline, Not built yet (on purpose), Request paths implemented in Phase 1, V1 Architecture (as built)

### Community 7 - "Project Plan: Solution Engineering Knowledge Workspace"
Cohesion: 0.09
Nodes (22): 0. Decided parameters, 1. What this is, 2. What the size of this changes, 3. Core principles, 4. Phase map, 5. Testing strategy (all phases), 6. Security posture, 7. Scalability posture (+14 more)

### Community 8 - "1. Security Engineering & Auditing"
Cohesion: 0.15
Nodes (12): 1. Security Engineering & Auditing, 2. Scalability & High-Performance Engineering, 3. Architecture Review Checklist, A. Authentication & Authorization, A. High-Scale Vector Search (`pgvector`), B. Database Connection Pooling, B. Input Validation & Injection Defense, C. Asynchronous & Queue-Backed Processing (+4 more)

### Community 9 - "compilerOptions"
Cohesion: 0.14
Nodes (13): compilerOptions, isolatedModules, jsx, lib, module, moduleResolution, noEmit, resolveJsonModule (+5 more)

### Community 10 - "test_generation.py"
Cohesion: 0.09
Nodes (31): _build_retrieval_filters(), Convert the generation request filters to retrieval filters., GroundedAnswer, GroundedAnswerChunk, LLMProvider, ABC, LLM provider interface. Phase 3 deliverable. The RAG layer never imports a…, One piece of a streaming response. (+23 more)

### Community 11 - "vercel.json"
Cohesion: 0.40
Nodes (4): buildCommand, installCommand, outputDirectory, $schema

### Community 12 - "graphify_preinvocation.py"
Cohesion: 0.50
Nodes (4): get_graph_stats(), main(), Path, Graphify PreInvocation hook script. Executed by Antigravity prior to model…

### Community 13 - "DocumentMetadataIn"
Cohesion: 0.06
Nodes (40): DocumentMetadataIn, BaseModel, field_validator, Why this document may not be marked `approved` yet., Metadata accepted on upload. Every field optional, every default safe., normalize(), Parse an incoming label, falling back to `default` when one is provided.…, parametrize (+32 more)

### Community 23 - "repo/backend/tests/test_permissions.py"
Cohesion: 0.17
Nodes (26): build_predicate_set(), predicates_for(), Assemble the full candidate predicate set: permissions, corpus, then filters., permission_predicate_count(), Used by the regression test that guards the Phase 2 exit criterion., Used by tests and by `dev_headers` mode. Deliberately narrow by default., restricted_principal(), fields() (+18 more)

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
Cohesion: 0.40
Nodes (4): 1. Graphify Knowledge Graph (Active & Enforced), 2. Test & Verification Guarantee, 3. Security & Scalability Priorities, Workspace Rules - Personal Knowledge AI

### Community 33 - "Workspace Rules - Personal Knowledge AI"
Cohesion: 0.40
Nodes (4): 1. Graphify Knowledge Graph (Active & Enforced), 2. Test & Verification Guarantee, 3. Security & Scalability Priorities, Workspace Rules - Personal Knowledge AI

### Community 35 - "EmbeddingProvider"
Cohesion: 0.18
Nodes (7): EmbeddingProvider, ABC, Embed chunk text for indexing., Embed a user question for retrieval., The RAG layer talks to this, never to a vendor SDK directly., functools, math

### Community 36 - "backend/app/jobs/worker.py"
Cohesion: 0.13
Nodes (20): app_api_routes, app_jobs_worker, loop(), The single ingestion worker. Runs either inside the API process (a daemon…, start_background_workers(), stop_background_workers(), worker_id(), lifespan() (+12 more)

### Community 37 - "UnsupportedFileType"
Cohesion: 0.20
Nodes (17): app_documents_sniffing, UnsupportedFileType, detect_file_type(), Extension-based type, kept for scripts and tests. The upload path uses…, decide_file_type(), normalize_extension(), Content wins. The declared extension is recorded, never trusted. Raises…, test_detect_file_type_covers_the_new_formats() (+9 more)

### Community 38 - "repo/backend/tests/test_scanning.py"
Cohesion: 0.14
Nodes (9): app_documents_scanning, HeuristicScanner, Structural refusal rules. Cheap, deterministic, and testable., fixture, Malware scanning. The heuristic backend is not an antivirus; these tests assert…, scanner(), test_disabled_scanner_is_recorded_not_hidden(), test_scan_or_raise_converts_a_finding_into_an_error() (+1 more)

### Community 39 - "repo/backend/tests/test_safety_limits.py"
Cohesion: 0.10
Nodes (29): app_documents_limits, ExtractionTimeout, Parsing exceeded its wall-clock budget. Tracked separately: it usually means a…, The file tripped a pre-parse safety limit (zip bomb, entity expansion,…, UnsafeFile, ArchiveReport, check_html_safety(), Deadline (+21 more)

### Community 40 - "generation/service.py"
Cohesion: 0.13
Nodes (38): Conversation, Message, add_message(), auto_title(), create_conversation(), delete_conversation(), get_conversation(), get_history() (+30 more)

### Community 41 - "backend/tests/test_permissions.py"
Cohesion: 0.17
Nodes (26): build_predicate_set(), predicates_for(), Assemble the full candidate predicate set: permissions, corpus, then filters., permission_predicate_count(), Used by the regression test that guards the Phase 2 exit criterion., Used by tests and by `dev_headers` mode. Deliberately narrow by default., restricted_principal(), fields() (+18 more)

### Community 42 - "test_generation_prompts.py"
Cohesion: 0.08
Nodes (32): app_documents_injection, build_context_block(), build_user_message(), format_history_turn(), format_source(), Versioned prompt templates for Phase 3 grounded generation. Project_Plan.md…, Build the user-turn content: context followed by the question., Format a conversation history turn for the model. (+24 more)

### Community 43 - "backend/app/api/routes/documents.py"
Cohesion: 0.26
Nodes (15): _metadata_from_form(), UploadFile, Bulk upload. Many files at once, or a whole folder drop from the browser. One…, upload_documents(), ApprovalIn, BulkUploadOut, ChunkOut, DocumentOut (+7 more)

### Community 44 - "backend/tests/test_search_sql.py"
Cohesion: 0.13
Nodes (26): app_retrieval_spec, _coerce(), compile_predicate(), compile_predicate_set(), ColumnElement, Exception, Translate the predicate IR into SQLAlchemy clauses. Thin on purpose. All of the…, AND everything together. The origin of a predicate never affects how it is… (+18 more)

### Community 45 - "repo/backend/tests/test_search_sql.py"
Cohesion: 0.13
Nodes (26): _coerce(), compile_predicate(), compile_predicate_set(), ColumnElement, Exception, Translate the predicate IR into SQLAlchemy clauses. Thin on purpose. All of the…, AND everything together. The origin of a predicate never affects how it is…, UnknownFilterField (+18 more)

### Community 46 - "IngestionJob"
Cohesion: 0.16
Nodes (26): IngestionJob, JobStatus, Durable ingestion queue. Deviation from the plan, on purpose: FastAPI…, claim(), enqueue(), fail(), _now(), datetime (+18 more)

### Community 47 - "repo/backend/app/documents/service.py"
Cohesion: 0.14
Nodes (24): DocumentStatus, DuplicateDocument, Content hash already exists in this workspace., DocumentStatus, Workspace, content_hash(), create_document(), delete_document() (+16 more)

### Community 48 - "app_core_config"
Cohesion: 0.09
Nodes (44): app_core_config, app_core_errors, app_db_migrations, app_db_models, app_db_session, app_documents_metadata, app_documents_service, app_jobs (+36 more)

### Community 49 - "UnsafeFile"
Cohesion: 0.11
Nodes (29): ExtractionTimeout, Parsing exceeded its wall-clock budget. Tracked separately: it usually means a…, The file tripped a pre-parse safety limit (zip bomb, entity expansion,…, UnsafeFile, ArchiveReport, check_html_safety(), Deadline, guard_extracted_size() (+21 more)

### Community 50 - "backend/tests/test_integration.py"
Cohesion: 0.12
Nodes (31): app_retrieval_permissions, app_retrieval_sql, DocumentChunk, _hydrate(), _ms(), SearchMode, Session, Hybrid retrieval: pgvector + PostgreSQL full-text search, fused with RRF. Shape… (+23 more)

### Community 51 - "repo/backend/tests/test_sniffing.py"
Cohesion: 0.16
Nodes (19): UnsupportedFileType, decide_file_type(), normalize_extension(), Decide what a file actually is from its bytes, not from its name.…, Content wins. The declared extension is recorded, never trusted. Raises…, Best-effort content identification of an in-memory upload., sniff(), _sniff_zip() (+11 more)

### Community 52 - "repo/backend/app/documents/extraction.py"
Cohesion: 0.11
Nodes (27): html_parser, ExtractionError, _decode(), _docx_heading_level(), _extract_docx(), _extract_html(), _extract_pdf(), _extract_pptx() (+19 more)

### Community 53 - "Principal"
Cohesion: 0.19
Nodes (19): Principal, delete_document(), document_chunks(), document_status(), get_document(), list_documents(), patch_metadata(), delete (+11 more)

### Community 54 - "app_core_logging"
Cohesion: 0.14
Nodes (9): app_core_logging, setup_logging(), logging, setup_logging(), main(), Run the ingestion worker as its own process. cd backend && python…, main(), Run the ingestion worker as its own process. cd backend && python… (+1 more)

### Community 55 - "_scoped"
Cohesion: 0.25
Nodes (16): delete_document(), document_chunks(), document_status(), get_document(), list_documents(), patch_metadata(), delete, get (+8 more)

### Community 56 - "test_rate_limit.py"
Cohesion: 0.16
Nodes (26): Per-org, per-month token budget for cost control. Project_Plan.md L195: per-org…, TokenBudget, check_rate_limit(), check_token_budget(), _current_month(), Session, UUID, Per-user rate limiting and per-org token budget enforcement. Project_Plan.md… (+18 more)

### Community 57 - "reciprocal_rank_fusion"
Cohesion: 0.09
Nodes (38): FusedHit, RankedList, Reciprocal Rank Fusion. Pure, deterministic, and unit-tested without a…, One retrieval branch's output, best first., 1-based rank per id, first occurrence wins., Fuse ranked lists. `score = sum(weight / (k + rank))` over the branches. Ties…, reciprocal_rank_fusion(), branches() (+30 more)

### Community 58 - "Sensitivity"
Cohesion: 0.16
Nodes (21): app_security_labels, Collateral metadata captured at ingest. **Deliberate deviation from…, get_or_create_default_org(), _parse_uuid(), Session, UUID, FastAPI dependency that turns a request into a `Principal`. Isolated from…, resolve_principal() (+13 more)

### Community 59 - "backend/tests/test_injection.py"
Cohesion: 0.12
Nodes (21): app_documents_chunking, InjectionFinding, neutralize_fences(), Prompt-injection containment. Project_Plan.md principle 7: "Ingested content is…, Strip forged delimiters so document text cannot close its own fence. This is…, Fence retrieved content for a prompt. Phase 3 must use this for every source., Flag instruction-like passages. Never blocks ingestion., scan_for_injection() (+13 more)

### Community 60 - "repo/backend/tests/test_injection.py"
Cohesion: 0.14
Nodes (18): re, InjectionFinding, neutralize_fences(), Prompt-injection containment. Project_Plan.md principle 7: "Ingested content is…, Strip forged delimiters so document text cannot close its own fence. This is…, Fence retrieved content for a prompt. Phase 3 must use this for every source., Flag instruction-like passages. Never blocks ingestion., scan_for_injection() (+10 more)

### Community 61 - "DuplicateDocument"
Cohesion: 0.11
Nodes (23): _as_http(), _filename_for_url(), ingest_paste(), ingest_url(), Exception, HTTPException, post, Ingest a URL through the SSRF-safe fetcher. (+15 more)

### Community 62 - "RetrievalFilters"
Cohesion: 0.09
Nodes (29): assert_enforced(), Permission-aware retrieval. Project_Plan.md Phase 2: "candidates are filtered…, corpus_predicates(), Origin, Predicate, PredicateSet, Retrieval filters, expressed as data. Why an intermediate representation…, Structural predicates. A superseded version or a half-ingested document is… (+21 more)

### Community 63 - "extract"
Cohesion: 0.16
Nodes (18): detect_file_type(), extract(), Path, Extract from raw bytes or a path. Bytes are preferred; paths are a convenience., Extension-based type, kept for scripts and tests. The upload path uses…, parametrize, Golden extraction tests: one fixture per format, plus one malformed file per…, Every failure must be a named application error with a readable message, never… (+10 more)

### Community 64 - "backend/app/db/models.py"
Cohesion: 0.21
Nodes (14): AccessGrant, Base, EvaluationQuestion, Organization, DeclarativeBase, Tenant root. Phase 0 will add row-level security keyed on this column; the…, Per-account read grant. Consumed by retrieval today, issued by an admin UI in…, SchemaMigration (+6 more)

### Community 65 - "repo/backend/app/api/routes/documents.py"
Cohesion: 0.21
Nodes (17): app_documents, app_documents_schemas, _metadata_from_form(), UploadFile, Bulk upload. Many files at once, or a whole folder drop from the browser. One…, upload_documents(), ApprovalIn, BulkUploadOut (+9 more)

### Community 66 - "_HtmlTextExtractor"
Cohesion: 0.16
Nodes (5): _HeadingTracker, _HtmlTextExtractor, HTMLParser, Stdlib parser: tolerant, and it never resolves external entities or DTDs., Maintains the current heading path, e.g. ('Licensing', 'Enterprise tier').

### Community 67 - "Block"
Cohesion: 0.27
Nodes (16): chunk_blocks(), Block, A structural unit of source text (a page, slide, sheet range, or section)., Chunking. Determinism first: the Phase 2 baseline is only comparable if…, The old grouping key was (page, section), which collapsed every heading-path…, `overlap = chunk_overlap or settings.chunk_overlap` silently turned an explicit…, test_anchor_label_is_human_readable(), test_chunk_indexes_are_sequential_and_deterministic() (+8 more)

### Community 68 - "RetrievalFilters"
Cohesion: 0.19
Nodes (18): Op, StrEnum, corpus_predicates(), Structural predicates. A superseded version or a half-ingested document is…, Caller-supplied narrowing. Every field is optional; none of them can widen what…, RetrievalFilters, Filter specification: every Phase 2 filter dimension maps to a predicate, and…, Phase 2 lists these as required, not optional: product, vendor, account,… (+10 more)

### Community 69 - "Block"
Cohesion: 0.26
Nodes (16): chunk_blocks(), Block, A structural unit of source text (a page, slide, sheet range, or section)., Chunking. Determinism first: the Phase 2 baseline is only comparable if…, The old grouping key was (page, section), which collapsed every heading-path…, `overlap = chunk_overlap or settings.chunk_overlap` silently turned an explicit…, test_anchor_label_is_human_readable(), test_chunk_indexes_are_sequential_and_deterministic() (+8 more)

### Community 70 - "PredicateSet"
Cohesion: 0.14
Nodes (10): assert_enforced(), Permission-aware retrieval. Project_Plan.md Phase 2: "candidates are filtered…, Op, Origin, Predicate, PredicateSet, StrEnum, Retrieval filters, expressed as data. Why an intermediate representation… (+2 more)

### Community 71 - "backend/tests/fixtures.py"
Cohesion: 0.14
Nodes (7): _escape(), make_pdf(), make_pdf_with_javascript(), make_zip_bomb(), Fixture builders for the ingestion tests. Everything is generated at test time…, A valid, minimal, multi-page text PDF. `pages[i]` is the lines of page i+1., An OOXML-shaped package whose members expand far beyond the limit.

### Community 72 - "pytest"
Cohesion: 0.17
Nodes (13): pytest, applied_migrations(), Engine, Idempotent, recorded schema migrations. The project had none:…, Apply every unapplied step. Returns the names that ran., run_migrations(), database(), _database_reachable() (+5 more)

### Community 73 - "repo/backend/tests/fixtures.py"
Cohesion: 0.14
Nodes (7): _escape(), make_pdf(), make_pdf_with_javascript(), make_zip_bomb(), Fixture builders for the ingestion tests. Everything is generated at test time…, A valid, minimal, multi-page text PDF. `pages[i]` is the lines of page i+1., An OOXML-shaped package whose members expand far beyond the limit.

### Community 74 - "backend/app/documents/sniffing.py"
Cohesion: 0.23
Nodes (9): Decide what a file actually is from its bytes, not from its name.…, Best-effort content identification of an in-memory upload., sniff(), _sniff_zip(), SniffResult, _try_decode(), TypeDecision, test_sniffs_every_supported_format() (+1 more)

### Community 75 - "dataclasses"
Cohesion: 0.13
Nodes (13): app_documents_anchors, app_documents_extraction, Citation anchors. A citation is only trustworthy if it resolves to one place in…, Deterministic, structure-aware chunking. Rules kept intentionally simple until…, _windows(), dataclasses, itertools, Anchor (+5 more)

### Community 76 - "Phase 1 and Phase 2, as built"
Cohesion: 0.14
Nodes (13): 1. The dependency the plan creates and this build had to resolve, 2. Phase 1: ingestion, 3. Deviation: metadata is not all mandatory at upload, 4. Honest gaps, 5. Phase 2: hybrid retrieval, 6. Running it, 7. What Phase 3 inherits, Changes made on purpose (+5 more)

### Community 77 - "What is left"
Cohesion: 0.14
Nodes (13): Also included (small, load-bearing extras), Build Status, Known deviations from the plan document, Phase 0 - Project setup, Phase 1 - Document ingestion, Phase 2 - Retrieval (not started), Phase 3 - Grounded generation (not started), Phase 4 - Evaluation (not started) (+5 more)

### Community 78 - "AppError"
Cohesion: 0.22
Nodes (12): AppError, PermissionDenied, PermissionFilterMissing, ProviderError, ProviderRateLimited, Exception, Base application error., External inference provider failed (network, 5xx, bad payload). (+4 more)

### Community 79 - "Phase 1 and Phase 2, as built"
Cohesion: 0.14
Nodes (13): 1. The dependency the plan creates and this build had to resolve, 2. Phase 1: ingestion, 3. Deviation: metadata is not all mandatory at upload, 4. Honest gaps, 5. Phase 2: hybrid retrieval, 6. Running it, 7. What Phase 3 inherits, Changes made on purpose (+5 more)

### Community 80 - "repo/backend/app/retrieval/search.py"
Cohesion: 0.20
Nodes (10): app_retrieval_fusion, get_logger(), Logger, _hydrate(), _ms(), Session, Hybrid retrieval: pgvector + PostgreSQL full-text search, fused with RRF. Shape…, SearchHit (+2 more)

### Community 81 - "Roadmap: Notes + Grounded AI"
Cohesion: 0.15
Nodes (12): Design rules, Feature parity map, Open decisions, Phase 10: Platform and ecosystem, Phase 6: Notes core, Phase 7: Linking and graph, Phase 8: Notebook studio, Phase 9: Differentiators (+4 more)

### Community 82 - "get_ocr_provider"
Cohesion: 0.16
Nodes (8): get_ocr_provider(), OcrProvider, NullOcrProvider, OcrProvider, The default. OCR is off unless someone deliberately turns it on. Reasoning…, OcrProvider, pytesseract + Pillow. Optional import: the API starts fine without either., TesseractOcrProvider

### Community 83 - "search_endpoint"
Cohesion: 0.33
Nodes (6): post, SearchIn, SearchOut, Session, Hybrid retrieval with its scores and fusion inputs exposed. This is the Phase 2…, search_endpoint()

### Community 84 - "io"
Cohesion: 0.21
Nodes (5): app_ocr_base, OcrProvider, ABC, Optical character recognition for PDFs with no text layer., io

### Community 85 - "repo/backend/app/db/models.py"
Cohesion: 0.16
Nodes (17): pgvector_sqlalchemy, AccessGrant, Base, Conversation, Document, EvaluationQuestion, IngestionJob, JobStatus (+9 more)

### Community 86 - "repo/backend/app/documents/scanning.py"
Cohesion: 0.21
Nodes (12): MalwareDetected, A malware scanner is configured but unreachable. Uploads fail closed., ScannerUnavailable, ClamAvScanner, get_scanner(), NullScanner, ABC, Malware scanning before parsing. Three backends behind one interface: * `none`… (+4 more)

### Community 87 - "repo/backend/tests/test_integration.py"
Cohesion: 0.25
Nodes (16): SearchMode, search(), ingest(), End-to-end tests against a real PostgreSQL with pgvector. Marked `requires_db`…, Phase 2 exit criterion. If this passes while the permission filter is deleted,…, test_a_grant_makes_account_material_visible(), test_a_restricted_chunk_never_appears_in_results(), test_a_superseded_version_never_appears_in_retrieval() (+8 more)

### Community 88 - "backend/app/documents/scanning.py"
Cohesion: 0.20
Nodes (10): ClamAvScanner, get_scanner(), NullScanner, ABC, Malware scanning before parsing. Three backends behind one interface: * `none`…, clamd INSTREAM client. No third-party dependency, no shell out., Scanner, ScanResult (+2 more)

### Community 89 - "Settings"
Cohesion: 0.25
Nodes (4): get_settings(), BaseSettings, All runtime configuration. Nothing model- or provider-specific is hard-coded., Settings

### Community 90 - "ask.py"
Cohesion: 0.07
Nodes (60): ask_endpoint(), ask_in_conversation_endpoint(), _conv_to_out(), create_conversation_endpoint(), delete_conversation_endpoint(), get_conversation_endpoint(), list_conversations_endpoint(), delete (+52 more)

### Community 91 - "Settings"
Cohesion: 0.18
Nodes (6): get_settings(), BaseSettings, field_validator, All runtime configuration. Nothing model- or provider-specific is hard-coded., Settings, pydantic_settings

### Community 92 - "llm/gemini.py"
Cohesion: 0.12
Nodes (15): get_logger(), Logger, _detect_refusal(), _extract_cited_indices(), GeminiLLMProvider, _map_citations(), retry, Gemini LLM provider for Phase 3 grounded generation. Uses httpx directly (same… (+7 more)

### Community 93 - "OcrProvider"
Cohesion: 0.40
Nodes (3): OcrProvider, ABC, Optical character recognition for PDFs with no text layer.

### Community 94 - "Build Status"
Cohesion: 0.22
Nodes (8): Build Status, Endpoints, Known deviations from the plan document, Phase 0, whenever it is scheduled, Phase 2's unfinished business, Phase status against Project_Plan.md, What is left before Phase 3 starts, Yours (config, not code)

### Community 95 - "repo/backend/tests/test_jobs.py"
Cohesion: 0.17
Nodes (13): Retry schedule. Pure arithmetic, kept separate so it can be tested without a DB., hashlib, backoff_seconds(), Retry schedule. Pure arithmetic, kept separate so it can be tested without a DB., Exponential backoff with deterministic jitter. Jitter is derived from…, Retry schedule and the worker's failure classification., Retrying a corrupt PDF four times just burns the single worker., test_attempts_are_one_based() (+5 more)

### Community 96 - "backend/app/retrieval/schemas.py"
Cohesion: 0.36
Nodes (7): BaseModel, The debug endpoint's contract: scores and fusion inputs are always exposed.…, Caller-supplied narrowing. Required, not optional, per Phase 2: every field…, SearchFiltersIn, SearchHitOut, SearchIn, SearchOut

### Community 97 - "repo/backend/app/jobs/queue.py"
Cohesion: 0.23
Nodes (15): claim(), enqueue(), fail(), _now(), datetime, Session, UUID, Durable ingestion queue on PostgreSQL. Why a table instead of… (+7 more)

### Community 98 - "backend/tests/conftest.py"
Cohesion: 0.19
Nodes (12): applied_migrations(), Engine, Idempotent, recorded schema migrations. The project had none:…, Apply every unapplied step. Returns the names that ran., run_migrations(), database(), _database_reachable(), db() (+4 more)

### Community 99 - "Sensitivity"
Cohesion: 0.25
Nodes (12): Collateral metadata captured at ingest. **Deliberate deviation from…, ApprovalState, Ownership, StrEnum, The controlled vocabularies Project_Plan.md treats as first-class. Kept in one…, Position on the confidentiality ladder. `vendor_restricted` ranks with…, Every ladder label a principal with `maximum` may read., Role (+4 more)

### Community 100 - "repo/backend/app/retrieval/schemas.py"
Cohesion: 0.36
Nodes (7): BaseModel, The debug endpoint's contract: scores and fusion inputs are always exposed.…, Caller-supplied narrowing. Required, not optional, per Phase 2: every field…, SearchFiltersIn, SearchHitOut, SearchIn, SearchOut

### Community 101 - "Anchor"
Cohesion: 0.14
Nodes (4): Anchor, Grouping key for chunking: a chunk never spans two anchors., Human-readable citation suffix, e.g. 'p. 12' or 'Pricing!A1:D20'., Chunk

### Community 102 - "backend/tests/test_jobs.py"
Cohesion: 0.24
Nodes (11): app_jobs_backoff, backoff_seconds(), Exponential backoff with deterministic jitter. Jitter is derived from…, Retry schedule and the worker's failure classification., Retrying a corrupt PDF four times just burns the single worker., test_attempts_are_one_based(), test_backoff_grows_exponentially_and_is_capped(), test_bad_files_are_never_retried_but_provider_failures_are() (+3 more)

### Community 103 - "owner_principal"
Cohesion: 0.11
Nodes (15): get_or_create_default_org(), Session, owner_principal(), Principal, UUID, Who is asking, and what they are allowed to read. Phase 0 (real authentication,…, The single collateral owner. Full read access by decision, not by accident., org() (+7 more)

### Community 104 - "TesseractOcrProvider"
Cohesion: 0.16
Nodes (8): get_ocr_provider(), OcrProvider, NullOcrProvider, OcrProvider, The default. OCR is off unless someone deliberately turns it on. Reasoning…, OcrProvider, pytesseract + Pillow. Optional import: the API starts fine without either., TesseractOcrProvider

### Community 105 - "Security & Scalability Architecture Rules"
Cohesion: 0.50
Nodes (3): 1. Security First Principles, 2. Scalability & High-Performance Engineering, Security & Scalability Architecture Rules

### Community 130 - "get_embedding_provider"
Cohesion: 0.22
Nodes (9): dependencies(), health(), get, Can the backend reach PostgreSQL, pgvector, object storage, and the embedding…, get_embedding_provider(), dependencies(), health(), get (+1 more)

### Community 131 - "backend/tests/test_scanning.py"
Cohesion: 0.27
Nodes (4): MalwareDetected, scan_or_raise(), Malware scanning. The heuristic backend is not an antivirus; these tests assert…, test_scan_or_raise_converts_a_finding_into_an_error()

### Community 132 - "GeminiEmbeddingProvider"
Cohesion: 0.24
Nodes (4): GeminiEmbeddingProvider, _normalize(), retry, Reduced-dimension Gemini vectors are not unit length; normalize for cosine…

### Community 133 - "repo/backend/app/jobs/worker.py"
Cohesion: 0.31
Nodes (8): DocumentChunk, process_document(), Run extraction through persistence. Owns its own session: the worker calls it., loop(), The single ingestion worker. Runs either inside the API process (a daemon…, Claim and run at most one job. Returns True if work was done., run_once(), worker_id()

### Community 134 - "job_stats"
Cohesion: 0.32
Nodes (8): job_stats(), JobOut, list_jobs(), BaseModel, get, Session, QueueStatsOut, Per-job status. Every failure is individually explainable and retryable, which…

### Community 136 - "job_stats"
Cohesion: 0.32
Nodes (8): job_stats(), JobOut, list_jobs(), BaseModel, get, Session, QueueStatsOut, Per-job status. Every failure is individually explainable and retryable, which…

### Community 137 - "HeuristicScanner"
Cohesion: 0.38
Nodes (4): HeuristicScanner, Structural refusal rules. Cheap, deterministic, and testable., fixture, scanner()

### Community 139 - "run_generation_eval.py"
Cohesion: 0.40
Nodes (5): json, load_dataset(), Path, Run generation evaluation suite for Phase 3 grounded answers. Project_Plan.md…, run_evaluation()

### Community 140 - "search_endpoint"
Cohesion: 0.33
Nodes (6): post, SearchIn, SearchOut, Session, Hybrid retrieval with its scores and fusion inputs exposed. This is the Phase 2…, search_endpoint()

### Community 141 - "Phase 3 Grounded Generation Baseline"
Cohesion: 0.40
Nodes (4): Adversarial Test Cases, Benchmark Summary, Phase 3 Grounded Generation Baseline, Refusal Test Cases

### Community 142 - "Phase 3: Grounded Answers, as built"
Cohesion: 0.40
Nodes (4): 1. Overview of Phase 3 Deliverables, 3. Intentional Changes & Design Decisions, 4. Honest Gaps & Future Work, Phase 3: Grounded Answers, as built

## Knowledge Gaps
- **177 isolated node(s):** `personal-knowledge-ai-backend`, `name`, `private`, `version`, `type` (+172 more)
  These have ≤1 connection - possible missing edges or undocumented components. (Counts symbols only; 816 node(s) total have ≤1 connection when file, concept and rationale nodes are included.)
- **38 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `Principal` connect `Principal` to `Document`, `job_stats`, `job_stats`, `search_endpoint`, `repo/backend/tests/test_permissions.py`, `generation/service.py`, `backend/tests/test_permissions.py`, `backend/app/api/routes/documents.py`, `repo/backend/app/documents/service.py`, `app_core_config`, `backend/tests/test_integration.py`, `_scoped`, `Sensitivity`, `DuplicateDocument`, `RetrievalFilters`, `repo/backend/app/api/routes/documents.py`, `search_endpoint`, `repo/backend/tests/test_integration.py`, `ask.py`?**
  _High betweenness centrality (0.075) - this node is a cross-community bridge._
- **Why does `DocumentMetadataIn` connect `DocumentMetadataIn` to `Document`, `repo/backend/app/api/routes/documents.py`, `owner_principal`, `backend/app/api/routes/documents.py`, `IngestionJob`, `repo/backend/app/documents/service.py`, `backend/tests/test_integration.py`, `Principal`, `repo/backend/tests/test_integration.py`, `_scoped`, `Sensitivity`, `DuplicateDocument`?**
  _High betweenness centrality (0.037) - this node is a cross-community bridge._
- **Why does `RetrievalFilters` connect `RetrievalFilters` to `RetrievalFilters`, `PredicateSet`, `generation/service.py`, `backend/tests/test_permissions.py`, `test_generation.py`, `backend/tests/test_search_sql.py`, `search_endpoint`, `repo/backend/tests/test_search_sql.py`, `app_core_config`, `backend/tests/test_integration.py`, `search_endpoint`, `repo/backend/tests/test_permissions.py`, `repo/backend/tests/test_integration.py`?**
  _High betweenness centrality (0.024) - this node is a cross-community bridge._
- **Are the 55 inferred relationships involving `Principal` (e.g. with `ask_endpoint()` and `ask_in_conversation_endpoint()`) actually correct?**
  _`Principal` has 55 INFERRED edges - model-reasoned connections that need verification._
- **Are the 51 inferred relationships involving `Document` (e.g. with `get_document()` and `ingest_paste()`) actually correct?**
  _`Document` has 51 INFERRED edges - model-reasoned connections that need verification._
- **Are the 27 inferred relationships involving `DocumentMetadataIn` (e.g. with `ingest_paste()` and `ingest_url()`) actually correct?**
  _`DocumentMetadataIn` has 27 INFERRED edges - model-reasoned connections that need verification._
- **Are the 21 inferred relationships involving `RetrievalFilters` (e.g. with `search_endpoint()` and `search()`) actually correct?**
  _`RetrievalFilters` has 21 INFERRED edges - model-reasoned connections that need verification._