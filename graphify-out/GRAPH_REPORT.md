# Graph Report - personal-knowledge-ai  (2026-09-20)

## Corpus Check
- 159 files · ~74,990 words
- Verdict: corpus is large enough that graph structure adds value.
- Unclassified: 6 file(s) not represented in the graph (top: (none) 3, .example 2, .css 1)

## Summary
- 1683 nodes · 4337 edges · 128 communities (76 shown, 52 thin omitted)
- Extraction: 88% EXTRACTED · 12% INFERRED · 0% AMBIGUOUS · INFERRED: 524 edges (avg confidence: 0.95)
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
- V1 Architecture (as built)
- Project Plan: Solution Engineering Knowledge Workspace
- Settings
- compilerOptions
- test_generation.py
- vercel.json
- test_permissions.py
- DocumentMetadataIn
- RetrievalFilters
- deps.py
- Roadmap: Notes + Grounded AI
- Evaluation Strategy (Phase 4)
- Graphify Knowledge Graph Rules
- workflows/graphify.md
- verify_project.py
- Graphify Synchronization and Knowledge Graph Navigation
- 2. Verification Runbook
- Workspace Rules - Personal Knowledge AI
- Principal
- Code Modification & Feature Verification Rules
- index.ts
- jobs/worker.py
- extract
- app_documents_scanning
- app_documents_limits
- test_conversations.py
- PredicateSet
- App.tsx
- query_product_impact
- app_retrieval_spec
- run_eval.py
- queue.py
- catalog.py
- sqlalchemy
- test_safety_limits.py
- test_integration.py
- db/models.py
- DocumentList.tsx
- app_api_routes
- app_core_logging
- _scoped
- test_rate_limit.py
- reciprocal_rank_fusion
- labels.py
- test_injection.py
- GroundedChat
- ingest_url
- test_search_sql.py
- app_core_config
- CatalogService
- app_documents
- _HtmlTextExtractor
- ProductIn
- app_core_errors
- app_db_migrations
- app_db_models
- errors.py
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
- GraphExplorer.tsx
- app_retrieval_permissions
- app_retrieval_schemas
- app_retrieval_search
- pydantic
- app_retrieval_sql
- app_security_deps
- app_security_labels
- app_security_principal
- Block
- app_jobs_backoff
- personal-knowledge-ai-backend
- OcrProvider
- tests
- test_generation_prompts.py
- ProductEdge
- catalog/models.py
- seeds.py
- documents.py
- fixtures.py
- generation/service.py
- test_jobs.py
- test_generation_adversarial.py
- GeminiEmbeddingProvider
- FakeEmbeddingProvider
- LocalStorage
- TestRelationPatterns
- search_endpoint
- catalog/__init__.py
- tempfile
- config.py
- EmbeddingProvider
- Phase 3 Grounded Generation Baseline

## God Nodes (most connected - your core abstractions)
1. `CatalogService` - 85 edges
2. `Principal` - 56 edges
3. `Document` - 45 edges
4. `DocumentMetadataIn` - 37 edges
5. `ProductEdge` - 36 edges
6. `AppError` - 33 edges
7. `extract()` - 32 edges
8. `RetrievalFilters` - 32 edges
9. `Product` - 31 edges
10. `Base` - 30 edges

## Surprising Connections (you probably didn't know these)
- `C. AI Edge Suggestion & Curation Workflow (`backend/app/catalog/curation.py`)` --references--> `EdgeSuggestionEngine`  [INFERRED]
  docs/PHASE4.md → backend/app/catalog/curation.py
- `Deliberate decisions` --references--> `ProviderRateLimited`  [INFERRED]
  docs/architecture.md → backend/app/core/errors.py
- `3. Intentional Changes & Design Decisions` --references--> `AskIn`  [INFERRED]
  docs/PHASE3.md → backend/app/generation/schemas.py
- `1. Overview of Phase 4 Deliverables` --references--> `detect_cycles_in_requires()`  [INFERRED]
  docs/PHASE4.md → backend/app/catalog/graph.py
- `1. Overview of Phase 4 Deliverables` --references--> `detect_contradictions()`  [INFERRED]
  docs/PHASE4.md → backend/app/catalog/graph.py

## Import Cycles
- None detected.

## Communities (128 total, 52 thin omitted)

### Community 0 - "documents/service.py"
Cohesion: 0.14
Nodes (32): ingest_paste(), Pasted text: discovery notes, an RFP extract, call notes typed up after the…, AppError, DuplicateDocument, Exception, Base application error., Content hash already exists in this workspace., Document (+24 more)

### Community 1 - "extraction.py"
Cohesion: 0.19
Nodes (23): ExtractionError, _decode(), _docx_heading_level(), _extract_docx(), _extract_html(), _extract_pdf(), _extract_pptx(), _extract_text() (+15 more)

### Community 2 - "StorageError"
Cohesion: 0.29
Nodes (5): StorageError, R2Storage, boto3, botocore_config, botocore_exceptions

### Community 3 - "package.json"
Cohesion: 0.11
Nodes (17): dependencies, react, react-dom, name, private, scripts, build, dev (+9 more)

### Community 4 - "ssrf.py"
Cohesion: 0.13
Nodes (28): A URL resolved to an address the fetcher refuses to touch., SsrfBlocked, classify_host(), fetch(), FetchedResource, is_blocked_address(), SSRF-safe URL fetching. Project_Plan.md Phase 1: "URL ingestion through an…, Return the denial reasons for a host. Empty list means allowed. Addresses may… (+20 more)

### Community 5 - "Personal Knowledge AI Workspace"
Cohesion: 0.10
Nodes (18): Deploy, Design rules this repo actually follows, Ingest a file without the UI, Personal Knowledge AI Workspace, Repository layout, Run it locally, Stack, Tests (+10 more)

### Community 6 - "V1 Architecture (as built)"
Cohesion: 0.33
Nodes (5): Deliberate decisions, Ingestion pipeline, Not built yet (on purpose), Request paths implemented in Phase 1, V1 Architecture (as built)

### Community 7 - "Project Plan: Solution Engineering Knowledge Workspace"
Cohesion: 0.06
Nodes (36): event_generator(), applied_migrations(), Idempotent, recorded schema migrations. The project had none:…, Apply every unapplied step. Returns the names that ran., run_migrations(), database(), _database_reachable(), db() (+28 more)

### Community 8 - "Settings"
Cohesion: 0.07
Nodes (20): 1. Security First Principles, 2. Scalability & High-Performance Engineering, Security & Scalability Architecture Rules, 1. Security Engineering & Auditing, 2. Scalability & High-Performance Engineering, 3. Architecture Review Checklist, A. Authentication & Authorization, A. High-Scale Vector Search (`pgvector`) (+12 more)

### Community 9 - "compilerOptions"
Cohesion: 0.14
Nodes (13): compilerOptions, isolatedModules, jsx, lib, module, moduleResolution, noEmit, resolveJsonModule (+5 more)

### Community 10 - "test_generation.py"
Cohesion: 0.06
Nodes (48): _build_retrieval_filters(), Convert the generation request filters to retrieval filters., GroundedAnswer, GroundedAnswerChunk, LLMProvider, ABC, LLM provider interface. Phase 3 deliverable. The RAG layer never imports a…, One piece of a streaming response. (+40 more)

### Community 11 - "vercel.json"
Cohesion: 0.40
Nodes (4): buildCommand, installCommand, outputDirectory, $schema

### Community 12 - "test_permissions.py"
Cohesion: 0.17
Nodes (27): build_predicate_set(), predicates_for(), Assemble the full candidate predicate set: permissions, corpus, then filters., Sensitivity, Used by tests and by `dev_headers` mode. Deliberately narrow by default., restricted_principal(), fields(), Permission-aware retrieval. Project_Plan.md Phase 2 exit criterion: "permission… (+19 more)

### Community 13 - "DocumentMetadataIn"
Cohesion: 0.11
Nodes (20): DocumentMetadataIn, BaseModel, field_validator, Why this document may not be marked `approved` yet., Metadata accepted on upload. Every field optional, every default safe., normalize(), Parse an incoming label, falling back to `default` when one is provided.…, parametrize (+12 more)

### Community 22 - "RetrievalFilters"
Cohesion: 0.19
Nodes (21): corpus_predicates(), Op, Origin, StrEnum, Retrieval filters, expressed as data. Why an intermediate representation…, Structural predicates. A superseded version or a half-ingested document is…, Caller-supplied narrowing. Every field is optional; none of them can widen what…, RetrievalFilters (+13 more)

### Community 23 - "deps.py"
Cohesion: 0.19
Nodes (14): job_stats(), JobOut, list_jobs(), BaseModel, get, Session, QueueStatsOut, Per-job status. Every failure is individually explainable and retryable, which… (+6 more)

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

### Community 33 - "Principal"
Cohesion: 0.15
Nodes (15): permission_predicate_count(), Used by the regression test that guards the Phase 2 exit criterion., Session, resolve_principal(), Position on the confidentiality ladder. `vendor_restricted` ranks with…, Every ladder label a principal with `maximum` may read., Role, sensitivities_up_to() (+7 more)

### Community 35 - "index.ts"
Cohesion: 0.17
Nodes (16): ChunkInspector(), Props, Props, api, AskResponse, BulkUploadOut, Conversation, ConversationListResponse (+8 more)

### Community 36 - "jobs/worker.py"
Cohesion: 0.12
Nodes (17): setup_logging(), loop(), The single ingestion worker. Runs either inside the API process (a daemon…, start_background_workers(), stop_background_workers(), worker_id(), lifespan(), get (+9 more)

### Community 37 - "extract"
Cohesion: 0.20
Nodes (15): extract(), Path, Extract from raw bytes or a path. Bytes are preferred; paths are a convenience., parametrize, Golden extraction tests: one fixture per format, plus one malformed file per…, Every failure must be a named application error with a readable message, never…, test_docx_builds_a_heading_path_and_keeps_tables(), test_html_drops_script_and_style_and_keeps_heading_path() (+7 more)

### Community 40 - "test_conversations.py"
Cohesion: 0.17
Nodes (30): Conversation, Message, add_message(), auto_title(), create_conversation(), delete_conversation(), get_conversation(), get_history() (+22 more)

### Community 41 - "PredicateSet"
Cohesion: 0.15
Nodes (9): PermissionFilterMissing, A retrieval query was assembled without its permission predicates. This is a…, assert_enforced(), Permission-aware retrieval. Project_Plan.md Phase 2: "candidates are filtered…, Predicate, PredicateSet, The tripwire. An empty or filter-only predicate set must never run., test_removing_the_permission_predicates_fails_loudly() (+1 more)

### Community 42 - "App.tsx"
Cohesion: 0.27
Nodes (6): App(), SearchExplorer(), UploadButton(), useDocuments(), frontend_src_index, react

### Community 43 - "query_product_impact"
Cohesion: 0.05
Nodes (47): compute_coverage(), detect_contradictions(), detect_cycles_in_requires(), dfs(), get_neighborhood(), Any, UUID, query_product_impact() (+39 more)

### Community 45 - "run_eval.py"
Cohesion: 0.27
Nodes (8): argparse, get_or_create_default_org(), main(), evaluate(), is_hit(), main(), Retrieval evaluation: vector-only vs keyword-only vs hybrid + RRF. cd backend…, render()

### Community 46 - "queue.py"
Cohesion: 0.22
Nodes (20): IngestionJob, JobStatus, Durable ingestion queue. Deviation from the plan, on purpose: FastAPI…, claim(), enqueue(), fail(), _now(), Session (+12 more)

### Community 47 - "catalog.py"
Cohesion: 0.13
Nodes (41): approve_edge(), assign_capability(), audit_graph_coverage(), audit_graph_integrity(), create_capability(), create_edge(), create_product(), create_reference_architecture() (+33 more)

### Community 48 - "sqlalchemy"
Cohesion: 0.09
Nodes (27): dependencies(), health(), get, Can the backend reach PostgreSQL, pgvector, object storage, and the embedding…, json, os, pathlib, resource (+19 more)

### Community 49 - "test_safety_limits.py"
Cohesion: 0.12
Nodes (28): ExtractionTimeout, Parsing exceeded its wall-clock budget. Tracked separately: it usually means a…, The file tripped a pre-parse safety limit (zip bomb, entity expansion,…, UnsafeFile, ArchiveReport, check_html_safety(), Deadline, guard_extracted_size() (+20 more)

### Community 50 - "test_integration.py"
Cohesion: 0.13
Nodes (29): DocumentChunk, _hydrate(), _ms(), Session, Hybrid retrieval: pgvector + PostgreSQL full-text search, fused with RRF. Shape…, search(), SearchHit, SearchResponse (+21 more)

### Community 51 - "db/models.py"
Cohesion: 0.12
Nodes (33): AccessGrant, Base, Capability, EvaluationQuestion, Organization, ProductCapability, Tenant root. Phase 0 will add row-level security keyed on this column; the…, Per-account read grant. Consumed by retrieval today, issued by an admin UI in… (+25 more)

### Community 52 - "DocumentList.tsx"
Cohesion: 0.38
Nodes (4): DocumentList(), formatSize(), Props, KnowledgeDocument

### Community 55 - "_scoped"
Cohesion: 0.23
Nodes (18): delete_document(), document_chunks(), document_status(), get_document(), list_documents(), patch_metadata(), delete, get (+10 more)

### Community 56 - "test_rate_limit.py"
Cohesion: 0.15
Nodes (28): GenerationRateLimited, The organization's token budget for this period has been reached., The user has exceeded their per-minute generation rate limit., TokenBudgetExhausted, Per-org, per-month token budget for cost control. Project_Plan.md L195: per-org…, TokenBudget, check_rate_limit(), check_token_budget() (+20 more)

### Community 57 - "reciprocal_rank_fusion"
Cohesion: 0.18
Nodes (19): FusedHit, RankedList, Reciprocal Rank Fusion. Pure, deterministic, and unit-tested without a…, One retrieval branch's output, best first., 1-based rank per id, first occurrence wins., Fuse ranked lists. `score = sum(weight / (k + rank))` over the branches. Ties…, reciprocal_rank_fusion(), branches() (+11 more)

### Community 58 - "labels.py"
Cohesion: 0.36
Nodes (7): Collateral metadata captured at ingest. **Deliberate deviation from…, ApprovalState, Ownership, StrEnum, The controlled vocabularies Project_Plan.md treats as first-class. Kept in one…, SourceType, enum

### Community 59 - "test_injection.py"
Cohesion: 0.15
Nodes (18): InjectionFinding, neutralize_fences(), Prompt-injection containment. Project_Plan.md principle 7: "Ingested content is…, Strip forged delimiters so document text cannot close its own fence. This is…, Fence retrieved content for a prompt. Phase 3 must use this for every source., Flag instruction-like passages. Never blocks ingestion., scan_for_injection(), wrap_untrusted() (+10 more)

### Community 60 - "GroundedChat"
Cohesion: 0.48
Nodes (6): GroundedChat(), handleDelete(), handleSend(), loadConversationDetails(), loadConversations(), loadConversationSources()

### Community 61 - "ingest_url"
Cohesion: 0.33
Nodes (6): _as_http(), _filename_for_url(), ingest_url(), Exception, Ingest a URL through the SSRF-safe fetcher., HTTPException

### Community 62 - "test_search_sql.py"
Cohesion: 0.13
Nodes (27): _coerce(), compile_predicate(), compile_predicate_set(), Exception, Translate the predicate IR into SQLAlchemy clauses. Thin on purpose. All of the…, AND everything together. The origin of a predicate never affects how it is…, UnknownFilterField, candidate_sql() (+19 more)

### Community 64 - "CatalogService"
Cohesion: 0.16
Nodes (7): Full integrity audit: cycle detection and contradiction detection., run_integrity_check(), slugify(), CatalogService, Session, UUID, ReferenceArchitecture

### Community 66 - "_HtmlTextExtractor"
Cohesion: 0.18
Nodes (5): _HeadingTracker, _HtmlTextExtractor, Stdlib parser: tolerant, and it never resolves external entities or DTDs., Maintains the current heading path, e.g. ('Licensing', 'Enterprise tier')., HTMLParser

### Community 67 - "ProductIn"
Cohesion: 0.12
Nodes (8): ProductEdgeIn, ProductIn, ProductUpdate, Any, field_validator, _make_product(), TestProductCRUD, TestResoldValidation

### Community 71 - "errors.py"
Cohesion: 0.10
Nodes (30): GenerationRefused, PermissionDenied, The caller's grants do not cover the resource. Surfaced as 404, never 403, so…, The model refused to answer because context was insufficient. This is not an…, UnsupportedFileType, detect_file_type(), Extension-based type, kept for scripts and tests. The upload path uses…, decide_file_type() (+22 more)

### Community 76 - "Phase 1 and Phase 2, as built"
Cohesion: 0.17
Nodes (11): 2. Phase 1: ingestion, 3. Deviation: metadata is not all mandatory at upload, 4. Honest gaps, 5. Phase 2: hybrid retrieval, 6. Running it, 7. What Phase 3 inherits, Changes made on purpose, How "filters before fusion" is guaranteed (+3 more)

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
Nodes (52): ask_endpoint(), ask_in_conversation_endpoint(), _conv_to_out(), create_conversation_endpoint(), delete_conversation_endpoint(), get_conversation_endpoint(), get_conversation_sources_endpoint(), list_conversations_endpoint() (+44 more)

### Community 91 - "devDependencies"
Cohesion: 0.33
Nodes (6): devDependencies, @types/react, @types/react-dom, typescript, vite, @vitejs/plugin-react

### Community 92 - "GraphExplorer.tsx"
Cohesion: 0.11
Nodes (23): EDGE_COLORS, GraphExplorer(), draw(), initSim(), OWNERSHIP_COLORS, SimNode, tick(), CapabilityOut (+15 more)

### Community 96 - "pydantic"
Cohesion: 0.31
Nodes (8): BaseModel, The debug endpoint's contract: scores and fusion inputs are always exposed.…, Caller-supplied narrowing. Required, not optional, per Phase 2: every field…, SearchFiltersIn, SearchHitOut, SearchIn, SearchOut, pydantic

### Community 101 - "Block"
Cohesion: 0.10
Nodes (24): Anchor, Citation anchors. A citation is only trustworthy if it resolves to one place in…, Grouping key for chunking: a chunk never spans two anchors., Human-readable citation suffix, e.g. 'p. 12' or 'Pricing!A1:D20'., Chunk, chunk_blocks(), Deterministic, structure-aware chunking. Rules kept intentionally simple until…, _windows() (+16 more)

### Community 104 - "OcrProvider"
Cohesion: 0.16
Nodes (7): OcrProvider, ABC, Optical character recognition for PDFs with no text layer., NullOcrProvider, The default. OCR is off unless someone deliberately turns it on. Reasoning…, pytesseract + Pillow. Optional import: the API starts fine without either., TesseractOcrProvider

### Community 106 - "test_generation_prompts.py"
Cohesion: 0.11
Nodes (23): build_context_block(), build_user_message(), format_history_turn(), format_source(), Versioned prompt templates for Phase 3 grounded generation. Project_Plan.md…, Build the user-turn content: context followed by the question., Format a conversation history turn for the model., Format one retrieved source chunk for the prompt. The `text` parameter is… (+15 more)

### Community 107 - "ProductEdge"
Cohesion: 0.17
Nodes (12): EdgeSuggestionEngine, Session, UUID, Scans document text for implied relationships between catalog products.…, EdgeStatus, Product, ProductEdge, _create_product() (+4 more)

### Community 108 - "catalog/models.py"
Cohesion: 0.26
Nodes (19): build_portfolio_graph(), Assembles node-link data for the visual graph., ConflictItem, CoverageReportOut, EdgeActionIn, EdgeSuggestionOut, GraphLink, GraphNode (+11 more)

### Community 112 - "seeds.py"
Cohesion: 0.20
Nodes (12): CapabilityIn, ProductCapabilityIn, ReferenceArchitectureIn, ReferenceArchitectureProductItem, Session, UUID, Populates the database with the Phase 4 seed catalog. Exit Criterion: - All 20…, seed_phase4_catalog() (+4 more)

### Community 113 - "documents.py"
Cohesion: 0.26
Nodes (15): _metadata_from_form(), Bulk upload. Many files at once, or a whole folder drop from the browser. One…, upload_documents(), ApprovalIn, BulkUploadOut, ChunkOut, DocumentOut, DocumentStatusOut (+7 more)

### Community 114 - "fixtures.py"
Cohesion: 0.14
Nodes (7): _escape(), make_pdf(), make_pdf_with_javascript(), make_zip_bomb(), Fixture builders for the ingestion tests. Everything is generated at test time…, A valid, minimal, multi-page text PDF. `pages[i]` is the lines of page i+1., An OOXML-shaped package whose members expand far beyond the limit.

### Community 115 - "generation/service.py"
Cohesion: 0.21
Nodes (12): get_logger(), ask(), ask_stream(), _prepare_context(), Session, UUID, RAG orchestration: retrieval → injection containment → LLM → cited answer. This…, Generate a grounded answer (synchronous). The full pipeline: 1. Rate limit… (+4 more)

### Community 116 - "test_jobs.py"
Cohesion: 0.21
Nodes (12): backoff_seconds(), Retry schedule. Pure arithmetic, kept separate so it can be tested without a DB., Exponential backoff with deterministic jitter. Jitter is derived from…, Retry schedule and the worker's failure classification., Retrying a corrupt PDF four times just burns the single worker., test_attempts_are_one_based(), test_backoff_grows_exponentially_and_is_capped(), test_bad_files_are_never_retried_but_provider_failures_are() (+4 more)

### Community 117 - "test_generation_adversarial.py"
Cohesion: 0.18
Nodes (10): Adversarial test suite for Phase 3 grounded generation. Project_Plan.md L201:…, Adversarial input attempting to close fences is neutralized., System prompt explicitly forbids guessing on pricing, products, or competitive…, When no sources are retrieved for an adversarial/out-of-domain question,…, Phase 3 architecture constraint: no tool calling or shell execution in…, test_adversarial_prompt_injection_neutralization(), test_fake_llm_refusal_on_empty_context(), test_no_tool_access_in_generation_layer() (+2 more)

### Community 118 - "GeminiEmbeddingProvider"
Cohesion: 0.27
Nodes (3): get_embedding_provider(), GeminiEmbeddingProvider, retry

### Community 120 - "LocalStorage"
Cohesion: 0.36
Nodes (3): LocalStorage, Path, Development-only stand-in for R2. Never use on Render (ephemeral filesystem).

### Community 122 - "search_endpoint"
Cohesion: 0.50
Nodes (4): post, Session, Hybrid retrieval with its scores and fusion inputs exposed. This is the Phase 2…, search_endpoint()

### Community 130 - "config.py"
Cohesion: 0.21
Nodes (6): LLM provider factory. Mirrors the embedding factory pattern: reads…, ObjectStorage, ABC, Original uploaded files live here. PostgreSQL only stores the key., functools, pydantic_settings

### Community 132 - "EmbeddingProvider"
Cohesion: 0.17
Nodes (8): EmbeddingProvider, ABC, Embed chunk text for indexing., Embed a user question for retrieval., The RAG layer talks to this, never to a vendor SDK directly., _normalize(), Reduced-dimension Gemini vectors are not unit length; normalize for cosine…, math

### Community 141 - "Phase 3 Grounded Generation Baseline"
Cohesion: 0.40
Nodes (4): Adversarial Test Cases, Benchmark Summary, Phase 3 Grounded Generation Baseline, Refusal Test Cases

## Knowledge Gaps
- **166 isolated node(s):** `personal-knowledge-ai-backend`, `name`, `private`, `version`, `type` (+161 more)
  These have ≤1 connection - possible missing edges or undocumented components. (Counts symbols only; 647 node(s) total have ≤1 connection when file, concept and rationale nodes are included.)
- **52 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `Principal` connect `Principal` to `documents/service.py`, `search_endpoint`, `PredicateSet`, `test_permissions.py`, `catalog.py`, `documents.py`, `test_integration.py`, `generation/service.py`, `deps.py`, `_scoped`, `ask.py`, `ingest_url`, `test_search_sql.py`?**
  _High betweenness centrality (0.061) - this node is a cross-community bridge._
- **Why does `resolve_principal()` connect `Principal` to `Personal Knowledge AI Workspace`, `test_permissions.py`, `run_eval.py`, `DocumentMetadataIn`, `catalog.py`, `documents.py`, `db/models.py`, `deps.py`, `ask.py`, `test_search_sql.py`?**
  _High betweenness centrality (0.056) - this node is a cross-community bridge._
- **Why does `Settings` connect `Settings` to `config.py`?**
  _High betweenness centrality (0.046) - this node is a cross-community bridge._
- **Are the 52 inferred relationships involving `CatalogService` (e.g. with `approve_edge()` and `assign_capability()`) actually correct?**
  _`CatalogService` has 52 INFERRED edges - model-reasoned connections that need verification._
- **Are the 36 inferred relationships involving `Principal` (e.g. with `ask_endpoint()` and `ask_in_conversation_endpoint()`) actually correct?**
  _`Principal` has 36 INFERRED edges - model-reasoned connections that need verification._
- **Are the 30 inferred relationships involving `Document` (e.g. with `get_product()` and `get_document()`) actually correct?**
  _`Document` has 30 INFERRED edges - model-reasoned connections that need verification._
- **Are the 10 inferred relationships involving `DocumentMetadataIn` (e.g. with `ingest_paste()` and `ingest_url()`) actually correct?**
  _`DocumentMetadataIn` has 10 INFERRED edges - model-reasoned connections that need verification._