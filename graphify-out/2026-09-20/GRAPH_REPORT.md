# Graph Report - personal-knowledge-ai  (2026-09-20)

## Corpus Check
- 159 files · ~74,990 words
- Verdict: corpus is large enough that graph structure adds value.
- Unclassified: 6 file(s) not represented in the graph (top: (none) 3, .example 2, .css 1)

## Summary
- 1706 nodes · 4276 edges · 126 communities (76 shown, 50 thin omitted)
- Extraction: 87% EXTRACTED · 13% INFERRED · 0% AMBIGUOUS · INFERRED: 571 edges (avg confidence: 0.94)
- Token cost: 0 input · 0 output

## Graph Freshness
- Built from commit: `6a0570d1`
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
- generation/service.py
- vercel.json
- Principal
- DocumentMetadataIn
- RetrievalFilters
- job_stats
- Roadmap: Notes + Grounded AI
- Evaluation Strategy (Phase 4)
- Graphify Knowledge Graph Rules
- workflows/graphify.md
- verify_project.py
- Graphify Synchronization and Knowledge Graph Navigation
- 2. Verification Runbook
- Workspace Rules - Personal Knowledge AI
- deps.py
- Code Modification & Feature Verification Rules
- index.ts
- jobs/worker.py
- extract
- app_documents_scanning
- app_documents_limits
- test_conversations.py
- PredicateSet
- App.tsx
- graph.py
- app_retrieval_spec
- bulk_load_test.py
- queue.py
- CatalogService
- pathlib
- test_safety_limits.py
- test_integration.py
- db/models.py
- DocumentList.tsx
- main.py
- migrations.py
- documents.py
- test_rate_limit.py
- test_fusion.py
- _mock_product
- generation/schemas.py
- GroundedChat
- GeminiLLMProvider
- test_search_sql.py
- Block
- UUID
- app_documents
- _HtmlTextExtractor
- CapabilityIn
- app_core_errors
- app_db_migrations
- app_db_models
- UnsupportedFileType
- ask_in_conversation_endpoint
- app_documents_chunking
- app_documents_extraction
- app_documents_anchors
- Phase 1 and Phase 2, as built
- What is left
- conftest.py
- app_documents_metadata
- retrieval/search.py
- Roadmap: Notes + Grounded AI
- app_documents_schemas
- 2. Architectural Components
- app_ocr_base
- app_documents_sniffing
- app_jobs
- Phase 3: Grounded Answers, as built
- scanning.py
- app_net_ssrf
- ask.py
- devDependencies
- GraphExplorer.tsx
- patch
- app_retrieval_schemas
- app_retrieval_search
- config.py
- app_retrieval_sql
- BaseModel
- field_validator
- chunking.py
- app_jobs_backoff
- personal-knowledge-ai-backend
- OcrProvider
- tests
- test_injection.py
- catalog/models.py
- ABC
- AppError
- fixtures.py
- ask
- retry
- StrEnum
- errors.py
- Path
- TestRelationPatterns
- PermissionFilterMissing
- catalog/__init__.py
- tempfile
- llm/base.py
- Phase 3 Grounded Generation Baseline

## God Nodes (most connected - your core abstractions)
1. `CatalogService` - 85 edges
2. `Document` - 41 edges
3. `DocumentMetadataIn` - 37 edges
4. `Principal` - 37 edges
5. `ProductEdge` - 36 edges
6. `AppError` - 33 edges
7. `RetrievalFilters` - 32 edges
8. `extract()` - 32 edges
9. `Base` - 30 edges
10. `Product` - 30 edges

## Surprising Connections (you probably didn't know these)
- `C. AI Edge Suggestion & Curation Workflow (`backend/app/catalog/curation.py`)` --references--> `EdgeSuggestionEngine`  [INFERRED]
  docs/PHASE4.md → backend/app/catalog/curation.py
- `Deliberate decisions` --references--> `ProviderRateLimited`  [INFERRED]
  docs/architecture.md → backend/app/core/errors.py
- `1. Overview of Phase 4 Deliverables` --references--> `detect_cycles_in_requires()`  [INFERRED]
  docs/PHASE4.md → backend/app/catalog/graph.py
- `1. Overview of Phase 4 Deliverables` --references--> `detect_contradictions()`  [INFERRED]
  docs/PHASE4.md → backend/app/catalog/graph.py
- `1. Overview of Phase 4 Deliverables` --references--> `compute_coverage()`  [INFERRED]
  docs/PHASE4.md → backend/app/catalog/graph.py

## Import Cycles
- None detected.

## Communities (126 total, 50 thin omitted)

### Community 0 - "documents/service.py"
Cohesion: 0.20
Nodes (23): Document, DocumentStatus, content_hash(), create_document(), delete_document(), enqueue_ingestion(), find_duplicate(), find_previous_version() (+15 more)

### Community 1 - "extraction.py"
Cohesion: 0.17
Nodes (24): ExtractionError, _decode(), _docx_heading_level(), _extract_docx(), _extract_html(), _extract_pdf(), _extract_pptx(), _extract_text() (+16 more)

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

### Community 6 - "V1 Architecture (as built)"
Cohesion: 0.33
Nodes (5): Deliberate decisions, Ingestion pipeline, Not built yet (on purpose), Request paths implemented in Phase 1, V1 Architecture (as built)

### Community 7 - "Project Plan: Solution Engineering Knowledge Workspace"
Cohesion: 0.09
Nodes (21): 0. Decided parameters, 1. What this is, 2. What the size of this changes, 3. Core principles, 4. Phase map, 5. Testing strategy (all phases), 6. Security posture, 7. Scalability posture (+13 more)

### Community 8 - "Settings"
Cohesion: 0.07
Nodes (20): 1. Security First Principles, 2. Scalability & High-Performance Engineering, Security & Scalability Architecture Rules, 1. Security Engineering & Auditing, 2. Scalability & High-Performance Engineering, 3. Architecture Review Checklist, A. Authentication & Authorization, A. High-Scale Vector Search (`pgvector`) (+12 more)

### Community 9 - "compilerOptions"
Cohesion: 0.14
Nodes (13): compilerOptions, isolatedModules, jsx, lib, module, moduleResolution, noEmit, resolveJsonModule (+5 more)

### Community 10 - "generation/service.py"
Cohesion: 0.10
Nodes (24): app_documents_injection, app_generation_rate_limit, app_llm_factory, app_llm_fake, app_llm_prompts, _build_retrieval_filters(), RAG orchestration: retrieval → injection containment → LLM → cited answer. This…, Convert the generation request filters to retrieval filters. (+16 more)

### Community 11 - "vercel.json"
Cohesion: 0.40
Nodes (4): buildCommand, installCommand, outputDirectory, $schema

### Community 12 - "Principal"
Cohesion: 0.14
Nodes (31): build_predicate_set(), predicates_for(), Assemble the full candidate predicate set: permissions, corpus, then filters., Sensitivity, owner_principal(), Principal, UUID, The single collateral owner. Full read access by decision, not by accident. (+23 more)

### Community 13 - "DocumentMetadataIn"
Cohesion: 0.09
Nodes (27): DocumentMetadataIn, BaseModel, field_validator, Collateral metadata captured at ingest. **Deliberate deviation from…, Why this document may not be marked `approved` yet., Metadata accepted on upload. Every field optional, every default safe., ApprovalState, normalize() (+19 more)

### Community 22 - "RetrievalFilters"
Cohesion: 0.18
Nodes (22): Permission-aware retrieval. Project_Plan.md Phase 2: "candidates are filtered…, corpus_predicates(), Op, Origin, Retrieval filters, expressed as data. Why an intermediate representation…, Structural predicates. A superseded version or a half-ingested document is…, Caller-supplied narrowing. Every field is optional; none of them can widen what…, RetrievalFilters (+14 more)

### Community 23 - "job_stats"
Cohesion: 0.32
Nodes (8): job_stats(), JobOut, list_jobs(), BaseModel, get, Session, QueueStatsOut, Per-job status. Every failure is individually explainable and retryable, which…

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
Cohesion: 0.44
Nodes (9): Path, py_compile, main(), print_section(), Project Test & Verification Runner. Executes verification steps across backend…, run_backend_tests(), verify_frontend(), verify_graphify() (+1 more)

### Community 30 - "Graphify Synchronization and Knowledge Graph Navigation"
Cohesion: 0.18
Nodes (10): 1. When to Use, 2. Navigating the Graph (Prompt Trigger), 3. Automatic & Manual Graph Synchronization, 4. Validation, A. Semantic Subgraph Query, B. Shortest Dependency Path, C. Node Explanation, Graphify Synchronization and Knowledge Graph Navigation (+2 more)

### Community 31 - "2. Verification Runbook"
Cohesion: 0.22
Nodes (8): 1. When to Use, 2. Verification Runbook, 3. Verification Checklist Before Concluding, Step 1: Run Unified Project Verification, Step 2: Backend Unit & Integration Tests, Step 3: Frontend Typechecking and Production Build, Step 4: Adding Tests for New Features, Test and Verification Skill

### Community 32 - "Workspace Rules - Personal Knowledge AI"
Cohesion: 0.18
Nodes (8): 1. Graphify Knowledge Graph (Active & Enforced), 2. Test & Verification Guarantee, 3. Security & Scalability Priorities, Workspace Rules - Personal Knowledge AI, 1. Graphify Knowledge Graph (Active & Enforced), 2. Test & Verification Guarantee, 3. Security & Scalability Priorities, Workspace Rules - Personal Knowledge AI

### Community 33 - "deps.py"
Cohesion: 0.16
Nodes (19): AccessGrant, Per-account read grant. Consumed by retrieval today, issued by an admin UI in…, get_db(), Session, get_or_create_default_org(), _parse_uuid(), Session, UUID (+11 more)

### Community 35 - "index.ts"
Cohesion: 0.17
Nodes (16): ChunkInspector(), Props, Props, api, AskResponse, BulkUploadOut, Conversation, ConversationListResponse (+8 more)

### Community 36 - "jobs/worker.py"
Cohesion: 0.14
Nodes (14): get_logger(), setup_logging(), loop(), The single ingestion worker. Runs either inside the API process (a daemon…, start_background_workers(), stop_background_workers(), worker_id(), lifespan() (+6 more)

### Community 37 - "extract"
Cohesion: 0.14
Nodes (21): detect_file_type(), extract(), Path, Extract from raw bytes or a path. Bytes are preferred; paths are a convenience., Extension-based type, kept for scripts and tests. The upload path uses…, parametrize, Golden extraction tests: one fixture per format, plus one malformed file per…, Every failure must be a named application error with a readable message, never… (+13 more)

### Community 40 - "test_conversations.py"
Cohesion: 0.14
Nodes (32): app_generation_conversations, Conversation, Message, add_message(), auto_title(), create_conversation(), delete_conversation(), get_conversation() (+24 more)

### Community 42 - "App.tsx"
Cohesion: 0.27
Nodes (6): App(), SearchExplorer(), UploadButton(), useDocuments(), frontend_src_index, react

### Community 43 - "graph.py"
Cohesion: 0.11
Nodes (31): compute_coverage(), detect_contradictions(), detect_cycles_in_requires(), dfs(), get_neighborhood(), Any, UUID, query_product_impact() (+23 more)

### Community 45 - "bulk_load_test.py"
Cohesion: 0.20
Nodes (11): argparse, resource, main(), Bulk ingestion test at 10x the real corpus. cd backend &&…, rss_mb(), synthetic_markdown(), evaluate(), is_hit() (+3 more)

### Community 46 - "queue.py"
Cohesion: 0.22
Nodes (20): IngestionJob, JobStatus, Durable ingestion queue. Deviation from the plan, on purpose: FastAPI…, claim(), enqueue(), fail(), _now(), Session (+12 more)

### Community 47 - "CatalogService"
Cohesion: 0.13
Nodes (46): approve_edge(), assign_capability(), audit_graph_coverage(), audit_graph_integrity(), create_capability(), create_edge(), create_product(), create_reference_architecture() (+38 more)

### Community 48 - "pathlib"
Cohesion: 0.09
Nodes (23): app_db_session, app_documents_service, app_security_deps, json, pathlib, get_graph_stats(), main(), Path (+15 more)

### Community 49 - "test_safety_limits.py"
Cohesion: 0.12
Nodes (28): ExtractionTimeout, Parsing exceeded its wall-clock budget. Tracked separately: it usually means a…, The file tripped a pre-parse safety limit (zip bomb, entity expansion,…, UnsafeFile, ArchiveReport, check_html_safety(), Deadline, guard_extracted_size() (+20 more)

### Community 50 - "test_integration.py"
Cohesion: 0.16
Nodes (25): DocumentChunk, _hydrate(), Session, search(), SearchHit, ingest(), org(), owner() (+17 more)

### Community 51 - "db/models.py"
Cohesion: 0.09
Nodes (39): EdgeSuggestionEngine, Session, UUID, Scans document text for implied relationships between catalog products.…, Base, Capability, EvaluationQuestion, Organization (+31 more)

### Community 52 - "DocumentList.tsx"
Cohesion: 0.38
Nodes (4): DocumentList(), formatSize(), Props, KnowledgeDocument

### Community 53 - "main.py"
Cohesion: 0.18
Nodes (10): app_api_routes, app_jobs_worker, dependencies(), health(), get, Can the backend reach PostgreSQL, pgvector, object storage, and the embedding…, get, root() (+2 more)

### Community 54 - "migrations.py"
Cohesion: 0.21
Nodes (10): app_core_config, app_core_logging, applied_migrations(), Idempotent, recorded schema migrations. The project had none:…, Apply every unapplied step. Returns the names that ran., run_migrations(), Engine, main() (+2 more)

### Community 55 - "documents.py"
Cohesion: 0.12
Nodes (37): _as_http(), delete_document(), document_chunks(), document_status(), _filename_for_url(), get_document(), ingest_paste(), ingest_url() (+29 more)

### Community 56 - "test_rate_limit.py"
Cohesion: 0.15
Nodes (28): The organization's token budget for this period has been reached., TokenBudgetExhausted, Per-org, per-month token budget for cost control. Project_Plan.md L195: per-org…, TokenBudget, check_rate_limit(), check_token_budget(), _current_month(), Session (+20 more)

### Community 57 - "test_fusion.py"
Cohesion: 0.08
Nodes (27): EmbeddingProvider, ABC, Embed chunk text for indexing., Embed a user question for retrieval., The RAG layer talks to this, never to a vendor SDK directly., FakeEmbeddingProvider, Deterministic hash-based vectors. For tests and offline development only., FusedHit (+19 more)

### Community 58 - "_mock_product"
Cohesion: 0.11
Nodes (15): _mock_edge(), _mock_product(), UUID, A conflicts_with B → query A yields B as incompatibility., A requires B, B conflicts_with C → query A yields C as indirect conflict., A integrates_with B → query A shows B as integration., A alternative_to B → query A shows B as alternative., Pending edges are excluded from impact computation. (+7 more)

### Community 59 - "generation/schemas.py"
Cohesion: 0.16
Nodes (19): AskFiltersIn, AskIn, AskOut, ConversationListOut, ConversationOut, MessageOut, BaseModel, Pydantic schemas for the Phase 3 generation API. All request/response models… (+11 more)

### Community 60 - "GroundedChat"
Cohesion: 0.48
Nodes (6): GroundedChat(), handleDelete(), handleSend(), loadConversationDetails(), loadConversations(), loadConversationSources()

### Community 61 - "GeminiLLMProvider"
Cohesion: 0.16
Nodes (10): _detect_refusal(), _extract_cited_indices(), GeminiLLMProvider, _map_citations(), Detect whether the model refused to answer due to insufficient context., Extract unique source indices cited in the answer text., Map cited source indices back to SourceMetadata from context_chunks., Gemini generation provider behind the LLMProvider interface. (+2 more)

### Community 62 - "test_search_sql.py"
Cohesion: 0.12
Nodes (28): app_security_labels, _coerce(), compile_predicate(), compile_predicate_set(), Exception, Translate the predicate IR into SQLAlchemy clauses. Thin on purpose. All of the…, AND everything together. The origin of a predicate never affects how it is…, UnknownFilterField (+20 more)

### Community 63 - "Block"
Cohesion: 0.27
Nodes (16): chunk_blocks(), Block, A structural unit of source text (a page, slide, sheet range, or section)., Chunking. Determinism first: the Phase 2 baseline is only comparable if…, The old grouping key was (page, section), which collapsed every heading-path…, `overlap = chunk_overlap or settings.chunk_overlap` silently turned an explicit…, test_anchor_label_is_human_readable(), test_chunk_indexes_are_sequential_and_deterministic() (+8 more)

### Community 66 - "_HtmlTextExtractor"
Cohesion: 0.18
Nodes (5): _HeadingTracker, _HtmlTextExtractor, Stdlib parser: tolerant, and it never resolves external entities or DTDs., Maintains the current heading path, e.g. ('Licensing', 'Enterprise tier')., HTMLParser

### Community 67 - "CapabilityIn"
Cohesion: 0.17
Nodes (6): CapabilityIn, ProductCapabilityIn, Any, _make_product(), TestCapabilities, TestProductCRUD

### Community 71 - "UnsupportedFileType"
Cohesion: 0.17
Nodes (19): UnsupportedFileType, decide_file_type(), normalize_extension(), Decide what a file actually is from its bytes, not from its name.…, Content wins. The declared extension is recorded, never trusted. Raises…, Best-effort content identification of an in-memory upload., sniff(), _sniff_zip() (+11 more)

### Community 72 - "ask_in_conversation_endpoint"
Cohesion: 0.24
Nodes (14): AskIn, AskOut, ask_endpoint(), ask_in_conversation_endpoint(), post, Return an SSE streaming response., Ask a question within an existing conversation (carries history)., Generate a grounded answer from the knowledge base. If `stream=true`, returns… (+6 more)

### Community 76 - "Phase 1 and Phase 2, as built"
Cohesion: 0.17
Nodes (11): 2. Phase 1: ingestion, 3. Deviation: metadata is not all mandatory at upload, 4. Honest gaps, 5. Phase 2: hybrid retrieval, 6. Running it, 7. What Phase 3 inherits, Changes made on purpose, How "filters before fusion" is guaranteed (+3 more)

### Community 77 - "What is left"
Cohesion: 0.14
Nodes (13): Also included (small, load-bearing extras), Build Status, Known deviations from the plan document, Phase 0 - Project setup, Phase 1 - Document ingestion, Phase 2 - Retrieval (not started), Phase 3 - Grounded generation (not started), Phase 4 - Evaluation (not started) (+5 more)

### Community 78 - "conftest.py"
Cohesion: 0.21
Nodes (10): event_generator(), database(), _database_reachable(), db(), org_id(), fixture, Test configuration. Two rules this file exists to enforce: * No test may make a…, 1. The dependency the plan creates and this build had to resolve (+2 more)

### Community 80 - "retrieval/search.py"
Cohesion: 0.18
Nodes (10): app_embeddings_factory, app_retrieval_fusion, app_retrieval_permissions, app_security_principal, _ms(), permission_predicate_count(), Principal, Hybrid retrieval: pgvector + PostgreSQL full-text search, fused with RRF. Shape… (+2 more)

### Community 81 - "Roadmap: Notes + Grounded AI"
Cohesion: 0.15
Nodes (12): Design rules, Feature parity map, Open decisions, Phase 10: Platform and ecosystem, Phase 6: Notes core, Phase 7: Linking and graph, Phase 8: Notebook studio, Phase 9: Differentiators (+4 more)

### Community 83 - "2. Architectural Components"
Cohesion: 0.25
Nodes (7): 2. Architectural Components, 3. Seed Catalog Summary (20 Products), 4. Exit Criteria Verification, B. Graph Traversal & Integrity Engine (`backend/app/catalog/graph.py`), C. AI Edge Suggestion & Curation Workflow (`backend/app/catalog/curation.py`), D. API Layer (`backend/app/api/routes/catalog.py`), Phase 4: Product Catalog and Typed Graph, as built

### Community 87 - "Phase 3: Grounded Answers, as built"
Cohesion: 0.50
Nodes (3): 1. Overview of Phase 3 Deliverables, 4. Honest Gaps & Future Work, Phase 3: Grounded Answers, as built

### Community 88 - "scanning.py"
Cohesion: 0.08
Nodes (30): MalwareDetected, A malware scanner is configured but unreachable. Uploads fail closed., ScannerUnavailable, ClamAvScanner, get_scanner(), HeuristicScanner, NullScanner, ABC (+22 more)

### Community 90 - "ask.py"
Cohesion: 0.15
Nodes (25): app_generation, _conv_to_out(), create_conversation_endpoint(), delete_conversation_endpoint(), get_conversation_endpoint(), get_conversation_sources_endpoint(), list_conversations_endpoint(), delete (+17 more)

### Community 91 - "devDependencies"
Cohesion: 0.33
Nodes (6): devDependencies, @types/react, @types/react-dom, typescript, vite, @vitejs/plugin-react

### Community 92 - "GraphExplorer.tsx"
Cohesion: 0.11
Nodes (23): EDGE_COLORS, GraphExplorer(), draw(), initSim(), OWNERSHIP_COLORS, SimNode, tick(), CapabilityOut (+15 more)

### Community 96 - "config.py"
Cohesion: 0.24
Nodes (9): BaseModel, The debug endpoint's contract: scores and fusion inputs are always exposed.…, Caller-supplied narrowing. Required, not optional, per Phase 2: every field…, SearchFiltersIn, SearchHitOut, SearchIn, SearchOut, pydantic (+1 more)

### Community 101 - "chunking.py"
Cohesion: 0.11
Nodes (9): Anchor, Citation anchors. A citation is only trustworthy if it resolves to one place in…, Grouping key for chunking: a chunk never spans two anchors., Human-readable citation suffix, e.g. 'p. 12' or 'Pricing!A1:D20'., Chunk, Deterministic, structure-aware chunking. Rules kept intentionally simple until…, _windows(), dataclasses (+1 more)

### Community 104 - "OcrProvider"
Cohesion: 0.17
Nodes (8): OcrProvider, ABC, Optical character recognition for PDFs with no text layer., get_ocr_provider(), NullOcrProvider, The default. OCR is off unless someone deliberately turns it on. Reasoning…, pytesseract + Pillow. Optional import: the API starts fine without either., TesseractOcrProvider

### Community 106 - "test_injection.py"
Cohesion: 0.05
Nodes (51): InjectionFinding, neutralize_fences(), Prompt-injection containment. Project_Plan.md principle 7: "Ingested content is…, Strip forged delimiters so document text cannot close its own fence. This is…, Fence retrieved content for a prompt. Phase 3 must use this for every source., Flag instruction-like passages. Never blocks ingestion., scan_for_injection(), wrap_untrusted() (+43 more)

### Community 108 - "catalog/models.py"
Cohesion: 0.11
Nodes (29): build_portfolio_graph(), Assembles node-link data for the visual graph., CoverageReportOut, EdgeActionIn, EdgeSuggestionOut, GraphLink, GraphNode, GraphQueryOut (+21 more)

### Community 113 - "AppError"
Cohesion: 0.22
Nodes (9): _metadata_from_form(), Bulk upload. Many files at once, or a whole folder drop from the browser. One…, upload_documents(), AppError, DuplicateDocument, Exception, Base application error., Content hash already exists in this workspace. (+1 more)

### Community 114 - "fixtures.py"
Cohesion: 0.12
Nodes (9): _escape(), make_pdf(), make_pdf_with_javascript(), make_zip_bomb(), Fixture builders for the ingestion tests. Everything is generated at test time…, A valid, minimal, multi-page text PDF. `pages[i]` is the lines of page i+1., An OOXML-shaped package whose members expand far beyond the limit., io (+1 more)

### Community 115 - "ask"
Cohesion: 0.23
Nodes (13): ask(), ask_stream(), _prepare_context(), Principal, Session, UUID, Generate a grounded answer (synchronous). The full pipeline: 1. Rate limit…, Generate a grounded answer with streaming. Yields GroundedAnswerChunk objects.… (+5 more)

### Community 118 - "errors.py"
Cohesion: 0.13
Nodes (15): GenerationRefused, PermissionDenied, ProviderError, ProviderRateLimited, External inference provider failed (network, 5xx, bad payload)., Provider returned 429. Tracked separately from retrieval failures., The caller's grants do not cover the resource. Surfaced as 404, never 403, so…, The model refused to answer because context was insufficient. This is not an… (+7 more)

### Community 122 - "PermissionFilterMissing"
Cohesion: 0.24
Nodes (10): post, Session, Hybrid retrieval with its scores and fusion inputs exposed. This is the Phase 2…, search_endpoint(), PermissionFilterMissing, A retrieval query was assembled without its permission predicates. This is a…, assert_enforced(), The tripwire. An empty or filter-only predicate set must never run. (+2 more)

### Community 130 - "llm/base.py"
Cohesion: 0.15
Nodes (13): ABC, GroundedAnswerChunk, LLMProvider, LLM provider interface. Phase 3 deliverable. The RAG layer never imports a…, One piece of a streaming response., Phase 3 provider interface. No vendor SDK leaks past this boundary., LLM provider factory. Mirrors the embedding factory pattern: reads…, Fake LLM provider for testing. Produces deterministic, canned responses that… (+5 more)

### Community 141 - "Phase 3 Grounded Generation Baseline"
Cohesion: 0.40
Nodes (4): Adversarial Test Cases, Benchmark Summary, Phase 3 Grounded Generation Baseline, Refusal Test Cases

## Knowledge Gaps
- **166 isolated node(s):** `D. API Layer (`backend/app/api/routes/catalog.py`)`, `3. Seed Catalog Summary (20 Products)`, `4. Exit Criteria Verification`, `Benchmark Summary`, `Refusal Test Cases` (+161 more)
  These have ≤1 connection - possible missing edges or undocumented components. (Counts symbols only; 652 node(s) total have ≤1 connection when file, concept and rationale nodes are included.)
- **50 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `CatalogService` connect `CatalogService` to `UUID`, `documents/service.py`, `CapabilityIn`, `graph.py`, `catalog/models.py`, `AppError`, `db/models.py`?**
  _High betweenness centrality (0.044) - this node is a cross-community bridge._
- **Why does `AppError` connect `AppError` to `UUID`, `extraction.py`, `StorageError`, `test_rate_limit.py`, `ssrf.py`, `documents/service.py`, `UnsupportedFileType`, `ask_in_conversation_endpoint`, `catalog/models.py`, `CatalogService`, `test_safety_limits.py`, `db/models.py`, `errors.py`, `documents.py`, `scanning.py`, `PermissionFilterMissing`?**
  _High betweenness centrality (0.044) - this node is a cross-community bridge._
- **Why does `Document` connect `documents/service.py` to `catalog/models.py`, `What is left`, `queue.py`, `CatalogService`, `retrieval/search.py`, `bulk_load_test.py`, `test_integration.py`, `db/models.py`, `pathlib`, `documents.py`, `test_search_sql.py`?**
  _High betweenness centrality (0.038) - this node is a cross-community bridge._
- **Are the 52 inferred relationships involving `CatalogService` (e.g. with `approve_edge()` and `assign_capability()`) actually correct?**
  _`CatalogService` has 52 INFERRED edges - model-reasoned connections that need verification._
- **Are the 26 inferred relationships involving `Document` (e.g. with `get_product()` and `get_document()`) actually correct?**
  _`Document` has 26 INFERRED edges - model-reasoned connections that need verification._
- **Are the 10 inferred relationships involving `DocumentMetadataIn` (e.g. with `ingest_paste()` and `ingest_url()`) actually correct?**
  _`DocumentMetadataIn` has 10 INFERRED edges - model-reasoned connections that need verification._
- **Are the 21 inferred relationships involving `Principal` (e.g. with `delete_document()` and `document_chunks()`) actually correct?**
  _`Principal` has 21 INFERRED edges - model-reasoned connections that need verification._