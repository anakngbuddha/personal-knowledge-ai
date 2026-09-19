# Graph Report - personal-knowledge-ai  (2026-09-20)

## Corpus Check
- 201 files · ~72,532 words
- Verdict: corpus is large enough that graph structure adds value.
- Unclassified: 6 file(s) not represented in the graph (top: .example 3, (none) 2, .css 1)

## Summary
- 1862 nodes · 4610 edges · 125 communities (88 shown, 37 thin omitted)
- Extraction: 88% EXTRACTED · 12% INFERRED · 0% AMBIGUOUS · INFERRED: 563 edges (avg confidence: 0.94)
- Token cost: 0 input · 0 output

## Graph Freshness
- Built from commit: `d59756cd`
- Run `git rev-parse HEAD` and compare to check if the graph is stale.
- Run `graphify update .` after code changes (no API cost).

## Community Hubs (Navigation)
- backend/app/documents/service.py
- backend/app/documents/extraction.py
- StorageError
- package.json
- backend/tests/test_ssrf.py
- Personal Knowledge AI Workspace
- V1 Architecture (as built)
- Project Plan: Solution Engineering Knowledge Workspace
- 1. Security Engineering & Auditing
- compilerOptions
- LLMProvider
- vercel.json
- app_core_errors
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
- backend/app/documents/scanning.py
- repo/backend/tests/test_safety_limits.py
- repo/scripts/bulk_load_test.py
- Sensitivity
- backend/app/net/ssrf.py
- backend/app/api/routes/documents.py
- backend/tests/test_search_sql.py
- repo/backend/tests/test_search_sql.py
- IngestionJob
- repo/backend/tests/test_integration.py
- app_core_config
- UnsafeFile
- backend/tests/test_integration.py
- repo/backend/tests/test_sniffing.py
- repo/backend/app/documents/extraction.py
- repo/backend/app/api/routes/documents.py
- repo/backend/app/documents/service.py
- Principal
- Deadline
- reciprocal_rank_fusion
- reciprocal_rank_fusion
- backend/tests/test_injection.py
- repo/backend/tests/test_injection.py
- Anchor
- RetrievalFilters
- extract
- Document
- repo/backend/tests/test_ssrf.py
- _HtmlTextExtractor
- Block
- dataclasses
- Block
- RetrievalFilters
- backend/tests/fixtures.py
- pytest
- repo/backend/tests/fixtures.py
- backend/app/documents/sniffing.py
- Anchor
- Phase 1 and Phase 2, as built
- What is left
- AppError
- Phase 1 and Phase 2, as built
- repo/backend/app/retrieval/search.py
- Roadmap: Notes + Grounded AI
- TesseractOcrProvider
- PermissionFilterMissing
- OcrProvider
- scripts/run_eval.py
- io
- backend/app/retrieval/search.py
- SsrfBlocked
- Settings
- AppError
- Settings
- get_logger
- OcrProvider
- Build Status
- backend/app/retrieval/schemas.py
- repo/backend/app/retrieval/schemas.py
- Chunk
- repo/scripts/run_eval.py
- TesseractOcrProvider
- Security & Scalability Architecture Rules
- personal-knowledge-ai-backend
- personal-knowledge-ai-backend
- tempfile

## God Nodes (most connected - your core abstractions)
1. `Principal` - 61 edges
2. `Document` - 60 edges
3. `DocumentMetadataIn` - 54 edges
4. `RetrievalFilters` - 47 edges
5. `Sensitivity` - 41 edges
6. `UnsafeFile` - 38 edges
7. `Block` - 35 edges
8. `DocumentMetadataIn` - 34 edges
9. `extract()` - 32 edges
10. `extract()` - 31 edges

## Surprising Connections (you probably didn't know these)
- `main()` --uses--> `Base`  [INFERRED]
  scripts/init_db.py → backend/app/db/models.py
- `_as_http()` --uses--> `AppError`  [INFERRED]
  repo/backend/app/api/routes/documents.py → backend/app/core/errors.py
- `set_approval()` --uses--> `AppError`  [INFERRED]
  repo/backend/app/api/routes/documents.py → backend/app/core/errors.py
- `upload_documents()` --uses--> `AppError`  [INFERRED]
  repo/backend/app/api/routes/documents.py → backend/app/core/errors.py
- `create_document()` --uses--> `AppError`  [INFERRED]
  repo/backend/app/documents/service.py → backend/app/core/errors.py

## Import Cycles
- None detected.

## Communities (125 total, 37 thin omitted)

### Community 0 - "backend/app/documents/service.py"
Cohesion: 0.20
Nodes (20): app_documents, DocumentStatus, Workspace, content_hash(), create_document(), delete_document(), enqueue_ingestion(), find_duplicate() (+12 more)

### Community 1 - "backend/app/documents/extraction.py"
Cohesion: 0.12
Nodes (37): ExtractionError, _decode(), _docx_heading_level(), extract(), _extract_docx(), _extract_html(), _extract_pdf(), _extract_pptx() (+29 more)

### Community 2 - "StorageError"
Cohesion: 0.12
Nodes (11): StorageError, ObjectStorage, ABC, Original uploaded files live here. PostgreSQL only stores the key., LocalStorage, Path, Development-only stand-in for R2. Never use on Render (ephemeral filesystem)., R2Storage (+3 more)

### Community 3 - "package.json"
Cohesion: 0.06
Nodes (38): dependencies, react, react-dom, devDependencies, @types/react, @types/react-dom, typescript, vite (+30 more)

### Community 4 - "backend/tests/test_ssrf.py"
Cohesion: 0.16
Nodes (20): classify_host(), is_blocked_address(), Return the denial reasons for a host. Empty list means allowed. Addresses may…, Validate a single URL. Returns (normalized_url, host)., Pure predicate over a single IP literal. This is the actual security boundary., resolve_host(), validate_url(), parametrize (+12 more)

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

### Community 10 - "LLMProvider"
Cohesion: 0.38
Nodes (4): GroundedAnswer, LLMProvider, ABC, Phase 3 lands here. The interface exists now so the RAG layer never imports a…

### Community 11 - "vercel.json"
Cohesion: 0.40
Nodes (4): buildCommand, installCommand, outputDirectory, $schema

### Community 12 - "app_core_errors"
Cohesion: 0.12
Nodes (20): app_core_errors, app_db_migrations, app_db_models, app_documents_metadata, app_documents_service, json, pathlib, Ingest local files through the real pipeline without going through HTTP. cd… (+12 more)

### Community 13 - "DocumentMetadataIn"
Cohesion: 0.06
Nodes (39): DocumentMetadataIn, BaseModel, field_validator, Why this document may not be marked `approved` yet., Metadata accepted on upload. Every field optional, every default safe., parametrize, Collateral metadata: safe defaults, explicit gaps, and a real promotion gate., Phase 9's vendor-collateral monitoring has nothing to re-check without it. (+31 more)

### Community 23 - "repo/backend/tests/test_permissions.py"
Cohesion: 0.14
Nodes (27): build_predicate_set(), predicates_for(), Assemble the full candidate predicate set: permissions, corpus, then filters., Principal, Used by tests and by `dev_headers` mode. Deliberately narrow by default., restricted_principal(), fields(), Permission-aware retrieval. Project_Plan.md Phase 2 exit criterion: "permission… (+19 more)

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
Cohesion: 0.06
Nodes (27): dependencies(), health(), get, Can the backend reach PostgreSQL, pgvector, object storage, and the embedding…, ProviderError, ProviderRateLimited, External inference provider failed (network, 5xx, bad payload)., Provider returned 429. Tracked separately from retrieval failures. (+19 more)

### Community 36 - "backend/app/jobs/worker.py"
Cohesion: 0.13
Nodes (21): app_api_routes, app_jobs_worker, loop(), The single ingestion worker. Runs either inside the API process (a daemon…, Claim and run at most one job. Returns True if work was done., run_once(), start_background_workers(), stop_background_workers() (+13 more)

### Community 37 - "UnsupportedFileType"
Cohesion: 0.20
Nodes (17): app_documents_sniffing, UnsupportedFileType, detect_file_type(), Extension-based type, kept for scripts and tests. The upload path uses…, decide_file_type(), normalize_extension(), Content wins. The declared extension is recorded, never trusted. Raises…, test_detect_file_type_covers_the_new_formats() (+9 more)

### Community 38 - "backend/app/documents/scanning.py"
Cohesion: 0.05
Nodes (41): app_documents_scanning, MalwareDetected, A malware scanner is configured but unreachable. Uploads fail closed., ScannerUnavailable, ClamAvScanner, get_scanner(), HeuristicScanner, NullScanner (+33 more)

### Community 39 - "repo/backend/tests/test_safety_limits.py"
Cohesion: 0.14
Nodes (24): app_documents_limits, ExtractionTimeout, Parsing exceeded its wall-clock budget. Tracked separately: it usually means a…, The file tripped a pre-parse safety limit (zip bomb, entity expansion,…, UnsafeFile, ArchiveReport, check_html_safety(), guard_extracted_size() (+16 more)

### Community 40 - "repo/scripts/bulk_load_test.py"
Cohesion: 0.24
Nodes (10): os, main(), Bulk ingestion test at 10x the real corpus. cd backend &&…, rss_mb(), synthetic_markdown(), resource, main(), Bulk ingestion test at 10x the real corpus. cd backend &&… (+2 more)

### Community 41 - "Sensitivity"
Cohesion: 0.13
Nodes (34): build_predicate_set(), predicates_for(), Assemble the full candidate predicate set: permissions, corpus, then filters., Every ladder label a principal with `maximum` may read., Role, sensitivities_up_to(), Sensitivity, owner_principal() (+26 more)

### Community 42 - "backend/app/net/ssrf.py"
Cohesion: 0.17
Nodes (14): fetch(), FetchedResource, SSRF-safe URL fetching. Project_Plan.md Phase 1: "URL ingestion through an…, Fetch a URL, validating every redirect hop., ipaddress, A URL resolved to an address the fetcher refuses to touch., SsrfBlocked, fetch() (+6 more)

### Community 43 - "backend/app/api/routes/documents.py"
Cohesion: 0.14
Nodes (27): _as_http(), _filename_for_url(), ingest_paste(), ingest_url(), _metadata_from_form(), Exception, HTTPException, post (+19 more)

### Community 44 - "backend/tests/test_search_sql.py"
Cohesion: 0.14
Nodes (25): _coerce(), compile_predicate(), compile_predicate_set(), ColumnElement, Exception, Translate the predicate IR into SQLAlchemy clauses. Thin on purpose. All of the…, AND everything together. The origin of a predicate never affects how it is…, UnknownFilterField (+17 more)

### Community 45 - "repo/backend/tests/test_search_sql.py"
Cohesion: 0.13
Nodes (25): _coerce(), compile_predicate(), compile_predicate_set(), ColumnElement, Exception, Translate the predicate IR into SQLAlchemy clauses. Thin on purpose. All of the…, AND everything together. The origin of a predicate never affects how it is…, UnknownFilterField (+17 more)

### Community 46 - "IngestionJob"
Cohesion: 0.05
Nodes (70): app_jobs_backoff, job_stats(), JobOut, list_jobs(), BaseModel, get, Session, QueueStatsOut (+62 more)

### Community 47 - "repo/backend/tests/test_integration.py"
Cohesion: 0.05
Nodes (76): pgvector_sqlalchemy, AccessGrant, Base, Conversation, Document, DocumentChunk, DocumentStatus, EvaluationQuestion (+68 more)

### Community 48 - "app_core_config"
Cohesion: 0.14
Nodes (25): app_core_config, app_db_session, app_retrieval_schemas, app_retrieval_search, app_retrieval_sql, app_security_deps, app_security_principal, get_db() (+17 more)

### Community 49 - "UnsafeFile"
Cohesion: 0.15
Nodes (26): The file tripped a pre-parse safety limit (zip bomb, entity expansion,…, UnsafeFile, ArchiveReport, check_html_safety(), guard_extracted_size(), inspect_ooxml(), ParseLimits, Pre-parse safety limits. Project_Plan.md asks for "parsing in a resource-… (+18 more)

### Community 50 - "backend/tests/test_integration.py"
Cohesion: 0.15
Nodes (27): DocumentChunk, Organization, Tenant root. Phase 0 will add row-level security keyed on this column; the…, process_document(), Run extraction through persistence. Owns its own session: the worker calls it., _hydrate(), SearchMode, Session (+19 more)

### Community 51 - "repo/backend/tests/test_sniffing.py"
Cohesion: 0.16
Nodes (19): UnsupportedFileType, decide_file_type(), normalize_extension(), Decide what a file actually is from its bytes, not from its name.…, Content wins. The declared extension is recorded, never trusted. Raises…, Best-effort content identification of an in-memory upload., sniff(), _sniff_zip() (+11 more)

### Community 52 - "repo/backend/app/documents/extraction.py"
Cohesion: 0.10
Nodes (28): ExtractionError, _decode(), _docx_heading_level(), _extract_docx(), _extract_html(), _extract_pdf(), _extract_pptx(), _extract_text() (+20 more)

### Community 53 - "repo/backend/app/api/routes/documents.py"
Cohesion: 0.10
Nodes (42): app_documents_schemas, _as_http(), delete_document(), document_chunks(), document_status(), _filename_for_url(), get_document(), ingest_paste() (+34 more)

### Community 54 - "repo/backend/app/documents/service.py"
Cohesion: 0.19
Nodes (9): app_core_logging, app_jobs, contextlib, datetime, Phase 1 ingestion pipeline. upload -> sniff -> scan -> hash -> dedup / version…, Run the ingestion worker as its own process. cd backend && python…, main(), Run the ingestion worker as its own process. cd backend && python… (+1 more)

### Community 55 - "Principal"
Cohesion: 0.21
Nodes (18): delete_document(), document_chunks(), document_status(), get_document(), list_documents(), patch_metadata(), delete, get (+10 more)

### Community 56 - "Deadline"
Cohesion: 0.11
Nodes (12): ExtractionTimeout, Parsing exceeded its wall-clock budget. Tracked separately: it usually means a…, Deadline, Deadline, Cooperative wall-clock budget. Extraction loops call `check()` per page., test_deadline_does_not_fire_early(), test_deadline_expires_and_names_what_timed_out(), Deadline (+4 more)

### Community 57 - "reciprocal_rank_fusion"
Cohesion: 0.22
Nodes (17): RankedList, One retrieval branch's output, best first., 1-based rank per id, first occurrence wins., Fuse ranked lists. `score = sum(weight / (k + rank))` over the branches. Ties…, reciprocal_rank_fusion(), branches(), Reciprocal Rank Fusion. Determinism is the requirement, not a nicety: the Phase…, `c` is only 3rd on vector but 1st on keyword, so it outranks `b` which is 2nd… (+9 more)

### Community 58 - "reciprocal_rank_fusion"
Cohesion: 0.22
Nodes (17): RankedList, One retrieval branch's output, best first., 1-based rank per id, first occurrence wins., Fuse ranked lists. `score = sum(weight / (k + rank))` over the branches. Ties…, reciprocal_rank_fusion(), branches(), Reciprocal Rank Fusion. Determinism is the requirement, not a nicety: the Phase…, `c` is only 3rd on vector but 1st on keyword, so it outranks `b` which is 2nd… (+9 more)

### Community 59 - "backend/tests/test_injection.py"
Cohesion: 0.16
Nodes (17): app_documents_chunking, app_documents_injection, neutralize_fences(), Strip forged delimiters so document text cannot close its own fence. This is…, Fence retrieved content for a prompt. Phase 3 must use this for every source., Flag instruction-like passages. Never blocks ingestion., scan_for_injection(), wrap_untrusted() (+9 more)

### Community 60 - "repo/backend/tests/test_injection.py"
Cohesion: 0.11
Nodes (21): InjectionFinding, Prompt-injection containment. Project_Plan.md principle 7: "Ingested content is…, re, InjectionFinding, neutralize_fences(), Prompt-injection containment. Project_Plan.md principle 7: "Ingested content is…, Strip forged delimiters so document text cannot close its own fence. This is…, Fence retrieved content for a prompt. Phase 3 must use this for every source. (+13 more)

### Community 61 - "Anchor"
Cohesion: 0.40
Nodes (3): Anchor, Grouping key for chunking: a chunk never spans two anchors., Human-readable citation suffix, e.g. 'p. 12' or 'Pricing!A1:D20'.

### Community 62 - "RetrievalFilters"
Cohesion: 0.11
Nodes (25): app_retrieval_spec, Permission-aware retrieval. Project_Plan.md Phase 2: "candidates are filtered…, corpus_predicates(), Op, Origin, Predicate, PredicateSet, StrEnum (+17 more)

### Community 63 - "extract"
Cohesion: 0.16
Nodes (18): detect_file_type(), extract(), Path, Extract from raw bytes or a path. Bytes are preferred; paths are a convenience., Extension-based type, kept for scripts and tests. The upload path uses…, parametrize, Golden extraction tests: one fixture per format, plus one malformed file per…, Every failure must be a named application error with a readable message, never… (+10 more)

### Community 64 - "Document"
Cohesion: 0.13
Nodes (23): app_security_labels, AccessGrant, Base, Conversation, Document, EvaluationQuestion, Message, DeclarativeBase (+15 more)

### Community 65 - "repo/backend/tests/test_ssrf.py"
Cohesion: 0.21
Nodes (14): app_net_ssrf, classify_host(), is_blocked_address(), Return the denial reasons for a host. Empty list means allowed. Addresses may…, Pure predicate over a single IP literal. This is the actual security boundary., parametrize, The SSRF fetcher's security boundary. The classifier is tested against resolved…, A public hostname is worthless as a signal; the resolved address decides. (+6 more)

### Community 66 - "_HtmlTextExtractor"
Cohesion: 0.16
Nodes (5): _HeadingTracker, _HtmlTextExtractor, HTMLParser, Stdlib parser: tolerant, and it never resolves external entities or DTDs., Maintains the current heading path, e.g. ('Licensing', 'Enterprise tier').

### Community 67 - "Block"
Cohesion: 0.27
Nodes (16): chunk_blocks(), Block, A structural unit of source text (a page, slide, sheet range, or section)., Chunking. Determinism first: the Phase 2 baseline is only comparable if…, The old grouping key was (page, section), which collapsed every heading-path…, `overlap = chunk_overlap or settings.chunk_overlap` silently turned an explicit…, test_anchor_label_is_human_readable(), test_chunk_indexes_are_sequential_and_deterministic() (+8 more)

### Community 68 - "dataclasses"
Cohesion: 0.15
Nodes (7): Citation anchors. A citation is only trustworthy if it resolves to one place in…, FusedHit, Reciprocal Rank Fusion. Pure, deterministic, and unit-tested without a…, dataclasses, Citation anchors. A citation is only trustworthy if it resolves to one place in…, FusedHit, Reciprocal Rank Fusion. Pure, deterministic, and unit-tested without a…

### Community 69 - "Block"
Cohesion: 0.26
Nodes (16): chunk_blocks(), Block, A structural unit of source text (a page, slide, sheet range, or section)., Chunking. Determinism first: the Phase 2 baseline is only comparable if…, The old grouping key was (page, section), which collapsed every heading-path…, `overlap = chunk_overlap or settings.chunk_overlap` silently turned an explicit…, test_anchor_label_is_human_readable(), test_chunk_indexes_are_sequential_and_deterministic() (+8 more)

### Community 70 - "RetrievalFilters"
Cohesion: 0.09
Nodes (28): enum, PermissionFilterMissing, A retrieval query was assembled without its permission predicates. This is a…, assert_enforced(), Permission-aware retrieval. Project_Plan.md Phase 2: "candidates are filtered…, corpus_predicates(), Op, Origin (+20 more)

### Community 71 - "backend/tests/fixtures.py"
Cohesion: 0.14
Nodes (7): _escape(), make_pdf(), make_pdf_with_javascript(), make_zip_bomb(), Fixture builders for the ingestion tests. Everything is generated at test time…, A valid, minimal, multi-page text PDF. `pages[i]` is the lines of page i+1., An OOXML-shaped package whose members expand far beyond the limit.

### Community 72 - "pytest"
Cohesion: 0.09
Nodes (25): applied_migrations(), Engine, Idempotent, recorded schema migrations. The project had none:…, Apply every unapplied step. Returns the names that ran., run_migrations(), database(), _database_reachable(), db() (+17 more)

### Community 73 - "repo/backend/tests/fixtures.py"
Cohesion: 0.14
Nodes (7): _escape(), make_pdf(), make_pdf_with_javascript(), make_zip_bomb(), Fixture builders for the ingestion tests. Everything is generated at test time…, A valid, minimal, multi-page text PDF. `pages[i]` is the lines of page i+1., An OOXML-shaped package whose members expand far beyond the limit.

### Community 74 - "backend/app/documents/sniffing.py"
Cohesion: 0.23
Nodes (9): Decide what a file actually is from its bytes, not from its name.…, Best-effort content identification of an in-memory upload., sniff(), _sniff_zip(), SniffResult, _try_decode(), TypeDecision, test_sniffs_every_supported_format() (+1 more)

### Community 75 - "Anchor"
Cohesion: 0.10
Nodes (11): app_documents_anchors, app_documents_extraction, Anchor, Grouping key for chunking: a chunk never spans two anchors., Human-readable citation suffix, e.g. 'p. 12' or 'Pricing!A1:D20'., Deterministic, structure-aware chunking. Rules kept intentionally simple until…, _windows(), itertools (+3 more)

### Community 76 - "Phase 1 and Phase 2, as built"
Cohesion: 0.14
Nodes (13): 1. The dependency the plan creates and this build had to resolve, 2. Phase 1: ingestion, 3. Deviation: metadata is not all mandatory at upload, 4. Honest gaps, 5. Phase 2: hybrid retrieval, 6. Running it, 7. What Phase 3 inherits, Changes made on purpose (+5 more)

### Community 77 - "What is left"
Cohesion: 0.14
Nodes (13): Also included (small, load-bearing extras), Build Status, Known deviations from the plan document, Phase 0 - Project setup, Phase 1 - Document ingestion, Phase 2 - Retrieval (not started), Phase 3 - Grounded generation (not started), Phase 4 - Evaluation (not started) (+5 more)

### Community 78 - "AppError"
Cohesion: 0.20
Nodes (12): AppError, DuplicateDocument, PermissionDenied, ProviderError, ProviderRateLimited, Exception, Base application error., External inference provider failed (network, 5xx, bad payload). (+4 more)

### Community 79 - "Phase 1 and Phase 2, as built"
Cohesion: 0.14
Nodes (13): 1. The dependency the plan creates and this build had to resolve, 2. Phase 1: ingestion, 3. Deviation: metadata is not all mandatory at upload, 4. Honest gaps, 5. Phase 2: hybrid retrieval, 6. Running it, 7. What Phase 3 inherits, Changes made on purpose (+5 more)

### Community 80 - "repo/backend/app/retrieval/search.py"
Cohesion: 0.20
Nodes (10): app_retrieval_fusion, _hydrate(), _ms(), permission_predicate_count(), Session, Hybrid retrieval: pgvector + PostgreSQL full-text search, fused with RRF. Shape…, Used by the regression test that guards the Phase 2 exit criterion., SearchHit (+2 more)

### Community 81 - "Roadmap: Notes + Grounded AI"
Cohesion: 0.15
Nodes (12): Design rules, Feature parity map, Open decisions, Phase 10: Platform and ecosystem, Phase 6: Notes core, Phase 7: Linking and graph, Phase 8: Notebook studio, Phase 9: Differentiators (+4 more)

### Community 82 - "TesseractOcrProvider"
Cohesion: 0.33
Nodes (3): OcrProvider, pytesseract + Pillow. Optional import: the API starts fine without either., TesseractOcrProvider

### Community 83 - "PermissionFilterMissing"
Cohesion: 0.12
Nodes (17): post, SearchIn, SearchOut, Session, Hybrid retrieval with its scores and fusion inputs exposed. This is the Phase 2…, search_endpoint(), PermissionFilterMissing, A retrieval query was assembled without its permission predicates. This is a… (+9 more)

### Community 84 - "OcrProvider"
Cohesion: 0.40
Nodes (3): OcrProvider, ABC, Optical character recognition for PDFs with no text layer.

### Community 85 - "scripts/run_eval.py"
Cohesion: 0.36
Nodes (6): argparse, evaluate(), is_hit(), main(), Retrieval evaluation: vector-only vs keyword-only vs hybrid + RRF. cd backend…, render()

### Community 86 - "io"
Cohesion: 0.20
Nodes (5): app_ocr_base, io, NullOcrProvider, OcrProvider, The default. OCR is off unless someone deliberately turns it on. Reasoning…

### Community 87 - "backend/app/retrieval/search.py"
Cohesion: 0.29
Nodes (6): app_retrieval_permissions, _ms(), permission_predicate_count(), Hybrid retrieval: pgvector + PostgreSQL full-text search, fused with RRF. Shape…, Used by the regression test that guards the Phase 2 exit criterion., SearchResponse

### Community 88 - "SsrfBlocked"
Cohesion: 0.36
Nodes (8): A URL resolved to an address the fetcher refuses to touch., SsrfBlocked, Validate a single URL. Returns (normalized_url, host)., validate_url(), test_embedded_credentials_are_blocked(), test_non_http_schemes_are_blocked(), test_unexpected_ports_are_blocked(), test_url_is_normalised_and_fragment_dropped()

### Community 89 - "Settings"
Cohesion: 0.22
Nodes (5): pydantic_settings, get_settings(), BaseSettings, All runtime configuration. Nothing model- or provider-specific is hard-coded., Settings

### Community 90 - "AppError"
Cohesion: 0.40
Nodes (5): AppError, PermissionDenied, Exception, Base application error., The caller's grants do not cover the resource. Surfaced as 404, never 403, so…

### Community 91 - "Settings"
Cohesion: 0.18
Nodes (6): get_settings(), BaseSettings, field_validator, All runtime configuration. Nothing model- or provider-specific is hard-coded., Settings, functools

### Community 92 - "get_logger"
Cohesion: 0.18
Nodes (8): get_logger(), Logger, setup_logging(), logging, get_logger(), Logger, setup_logging(), main()

### Community 93 - "OcrProvider"
Cohesion: 0.40
Nodes (3): OcrProvider, ABC, Optical character recognition for PDFs with no text layer.

### Community 94 - "Build Status"
Cohesion: 0.22
Nodes (8): Build Status, Endpoints, Known deviations from the plan document, Phase 0, whenever it is scheduled, Phase 2's unfinished business, Phase status against Project_Plan.md, What is left before Phase 3 starts, Yours (config, not code)

### Community 96 - "backend/app/retrieval/schemas.py"
Cohesion: 0.36
Nodes (7): BaseModel, The debug endpoint's contract: scores and fusion inputs are always exposed.…, Caller-supplied narrowing. Required, not optional, per Phase 2: every field…, SearchFiltersIn, SearchHitOut, SearchIn, SearchOut

### Community 100 - "repo/backend/app/retrieval/schemas.py"
Cohesion: 0.36
Nodes (7): BaseModel, The debug endpoint's contract: scores and fusion inputs are always exposed.…, Caller-supplied narrowing. Required, not optional, per Phase 2: every field…, SearchFiltersIn, SearchHitOut, SearchIn, SearchOut

### Community 103 - "repo/scripts/run_eval.py"
Cohesion: 0.23
Nodes (10): get_or_create_default_org(), _parse_uuid(), Session, UUID, resolve_principal(), evaluate(), is_hit(), main() (+2 more)

### Community 104 - "TesseractOcrProvider"
Cohesion: 0.16
Nodes (8): get_ocr_provider(), OcrProvider, NullOcrProvider, OcrProvider, The default. OCR is off unless someone deliberately turns it on. Reasoning…, OcrProvider, pytesseract + Pillow. Optional import: the API starts fine without either., TesseractOcrProvider

### Community 105 - "Security & Scalability Architecture Rules"
Cohesion: 0.50
Nodes (3): 1. Security First Principles, 2. Scalability & High-Performance Engineering, Security & Scalability Architecture Rules

## Knowledge Gaps
- **172 isolated node(s):** `personal-knowledge-ai-backend`, `name`, `private`, `version`, `type` (+167 more)
  These have ≤1 connection - possible missing edges or undocumented components. (Counts symbols only; 717 node(s) total have ≤1 connection when file, concept and rationale nodes are included.)
- **37 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `Principal` connect `Principal` to `backend/app/documents/service.py`, `repo/scripts/run_eval.py`, `Sensitivity`, `backend/app/api/routes/documents.py`, `IngestionJob`, `repo/backend/tests/test_integration.py`, `app_core_config`, `repo/backend/app/retrieval/search.py`, `backend/tests/test_integration.py`, `PermissionFilterMissing`, `repo/backend/tests/test_permissions.py`, `repo/backend/app/api/routes/documents.py`, `backend/app/retrieval/search.py`, `RetrievalFilters`?**
  _High betweenness centrality (0.042) - this node is a cross-community bridge._
- **Why does `Document` connect `Document` to `backend/app/documents/service.py`, `repo/scripts/bulk_load_test.py`, `Sensitivity`, `backend/app/api/routes/documents.py`, `backend/tests/test_search_sql.py`, `repo/backend/tests/test_search_sql.py`, `DocumentMetadataIn`, `repo/backend/tests/test_integration.py`, `repo/backend/app/retrieval/search.py`, `backend/tests/test_integration.py`, `repo/backend/app/api/routes/documents.py`, `backend/app/retrieval/search.py`, `Principal`?**
  _High betweenness centrality (0.023) - this node is a cross-community bridge._
- **Why does `DocumentMetadataIn` connect `DocumentMetadataIn` to `Document`, `backend/app/documents/service.py`, `repo/scripts/bulk_load_test.py`, `Sensitivity`, `backend/app/api/routes/documents.py`, `repo/backend/tests/test_integration.py`, `backend/tests/test_integration.py`, `repo/backend/app/api/routes/documents.py`, `Principal`?**
  _High betweenness centrality (0.020) - this node is a cross-community bridge._
- **Are the 44 inferred relationships involving `Principal` (e.g. with `delete_document()` and `document_chunks()`) actually correct?**
  _`Principal` has 44 INFERRED edges - model-reasoned connections that need verification._
- **Are the 51 inferred relationships involving `Document` (e.g. with `get_document()` and `ingest_paste()`) actually correct?**
  _`Document` has 51 INFERRED edges - model-reasoned connections that need verification._
- **Are the 27 inferred relationships involving `DocumentMetadataIn` (e.g. with `ingest_paste()` and `ingest_url()`) actually correct?**
  _`DocumentMetadataIn` has 27 INFERRED edges - model-reasoned connections that need verification._
- **Are the 21 inferred relationships involving `RetrievalFilters` (e.g. with `search_endpoint()` and `search()`) actually correct?**
  _`RetrievalFilters` has 21 INFERRED edges - model-reasoned connections that need verification._