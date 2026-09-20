# Graph Report - personal-knowledge-ai  (2026-09-20)

## Corpus Check
- 159 files · ~73,550 words
- Verdict: corpus is large enough that graph structure adds value.
- Unclassified: 6 file(s) not represented in the graph (top: (none) 3, .example 2, .css 1)

## Summary
- 1680 nodes · 4337 edges · 139 communities (78 shown, 61 thin omitted)
- Extraction: 88% EXTRACTED · 12% INFERRED · 0% AMBIGUOUS · INFERRED: 531 edges (avg confidence: 0.95)
- Token cost: 0 input · 0 output

## Graph Freshness
- Built from commit: `54a3d41d`
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
- Project Plan: Solution Engineering Knowledge Workspace (Enterprise Multi-Tenant)
- Settings
- compilerOptions
- test_generation.py
- vercel.json
- test_permissions.py
- catalog/models.py
- retrieval/search.py
- jobs.py
- Roadmap: Notes + Grounded AI
- Evaluation Strategy (Phase 4)
- Graphify Knowledge Graph Rules
- workflows/graphify.md
- verify_project.py
- Graphify Synchronization and Knowledge Graph Navigation
- 2. Verification Runbook
- Workspace Rules - Personal Knowledge AI
- seeds.py
- Code Modification & Feature Verification Rules
- index.ts
- test_injection.py
- extract
- app_documents_scanning
- app_documents_limits
- test_conversations.py
- PredicateSet
- App.tsx
- test_graph_integrity.py
- app_retrieval_spec
- UUID
- queue.py
- CatalogService
- sqlalchemy
- test_safety_limits.py
- test_integration.py
- jobs/worker.py
- DocumentList.tsx
- dependencies
- app_core_config
- documents.py
- test_rate_limit.py
- reciprocal_rank_fusion
- test_graph_query.py
- db/models.py
- GroundedChat
- GeminiLLMProvider
- test_search_sql.py
- pytest
- EmbeddingProvider
- app_documents
- _HtmlTextExtractor
- 1. Security Engineering & Auditing
- app_core_errors
- app_db_migrations
- app_db_models
- UnsupportedFileType
- test_generation_adversarial.py
- app_documents_chunking
- app_documents_extraction
- app_documents_anchors
- Phase 1 and Phase 2, as built
- What is left
- _make_product
- app_documents_metadata
- Principal
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
- llm/gemini.py
- app_retrieval_schemas
- app_retrieval_search
- routes/search.py
- app_retrieval_sql
- LocalStorage
- config.py
- app_api_routes
- Block
- app_jobs_backoff
- personal-knowledge-ai-backend
- OcrProvider
- tests
- test_generation_prompts.py
- app_core_logging
- app_db_session
- app_documents_injection
- injection.py
- fixtures.py
- generation/service.py
- app_documents_service
- app_embeddings_factory
- errors.py
- app_generation
- app_generation_conversations
- TestRelationPatterns
- app_generation_rate_limit
- catalog/__init__.py
- app_jobs_worker
- app_llm_factory
- app_llm_fake
- app_llm_prompts
- app_retrieval_fusion
- tempfile
- GroundedAnswer
- app_retrieval_permissions
- app_security_deps
- app_security_labels
- app_security_principal
- _build_retrieval_filters
- test_prompt_version_is_valid_semver
- test_system_prompt_grounding_rules
- Phase 3 Grounded Generation Baseline

## God Nodes (most connected - your core abstractions)
1. `CatalogService` - 85 edges
2. `Principal` - 56 edges
3. `Document` - 45 edges
4. `ProductEdge` - 37 edges
5. `DocumentMetadataIn` - 37 edges
6. `AppError` - 33 edges
7. `extract()` - 32 edges
8. `RetrievalFilters` - 32 edges
9. `Product` - 31 edges
10. `Base` - 30 edges

## Surprising Connections (you probably didn't know these)
- `C. AI Edge Suggestion & Curation Workflow (`backend/app/catalog/curation.py`)` --references--> `EdgeSuggestionEngine`  [INFERRED]
  docs/PHASE4.md → backend/app/catalog/curation.py
- `C. Secrets & Environment Isolation` --references--> `Settings`  [INFERRED]
  .agents/skills/security-and-scalability/SKILL.md → backend/app/core/config.py
- `Deliberate decisions` --references--> `ProviderRateLimited`  [INFERRED]
  docs/architecture.md → backend/app/core/errors.py
- `Phase 8: Solution Composer & Post-Sales Playbooks` --references--> `ProductEdge`  [INFERRED]
  Project_Plan.md → backend/app/db/models.py
- `3. Intentional Changes & Design Decisions` --references--> `AskIn`  [INFERRED]
  docs/PHASE3.md → backend/app/generation/schemas.py

## Import Cycles
- None detected.

## Communities (139 total, 61 thin omitted)

### Community 0 - "documents/service.py"
Cohesion: 0.17
Nodes (26): AppError, DuplicateDocument, Exception, Base application error., Content hash already exists in this workspace., Document, DocumentStatus, content_hash() (+18 more)

### Community 1 - "extraction.py"
Cohesion: 0.14
Nodes (25): ExtractionError, _decode(), _docx_heading_level(), _extract_docx(), _extract_html(), _extract_pdf(), _extract_pptx(), _extract_text() (+17 more)

### Community 2 - "StorageError"
Cohesion: 0.29
Nodes (5): StorageError, R2Storage, boto3, botocore_config, botocore_exceptions

### Community 3 - "package.json"
Cohesion: 0.11
Nodes (17): dependencies, react, react-dom, name, private, scripts, build, dev (+9 more)

### Community 4 - "ssrf.py"
Cohesion: 0.12
Nodes (29): A URL resolved to an address the fetcher refuses to touch., SsrfBlocked, classify_host(), fetch(), FetchedResource, is_blocked_address(), SSRF-safe URL fetching. Project_Plan.md Phase 1: "URL ingestion through an…, Return the denial reasons for a host. Empty list means allowed. Addresses may… (+21 more)

### Community 5 - "Personal Knowledge AI Workspace"
Cohesion: 0.13
Nodes (13): Deploy, Design rules this repo actually follows, Ingest a file without the UI, Personal Knowledge AI Workspace, Repository layout, Run it locally, Stack, Tests (+5 more)

### Community 6 - "V1 Architecture (as built)"
Cohesion: 0.33
Nodes (5): Deliberate decisions, Ingestion pipeline, Not built yet (on purpose), Request paths implemented in Phase 1, V1 Architecture (as built)

### Community 7 - "Project Plan: Solution Engineering Knowledge Workspace (Enterprise Multi-Tenant)"
Cohesion: 0.10
Nodes (19): LLMProvider, ABC, Phase 3 provider interface. No vendor SDK leaks past this boundary., 0. Decided Parameters, 1. What This Is, 2. Core Principles, 3. Restructured Phase Map, 4. Documentation Hygiene & Repo Synchronization (+11 more)

### Community 8 - "Settings"
Cohesion: 0.14
Nodes (8): 1. Security First Principles, 2. Scalability & High-Performance Engineering, Security & Scalability Architecture Rules, get_settings(), field_validator, All runtime configuration. Nothing model- or provider-specific is hard-coded., Settings, BaseSettings

### Community 9 - "compilerOptions"
Cohesion: 0.14
Nodes (13): compilerOptions, isolatedModules, jsx, lib, module, moduleResolution, noEmit, resolveJsonModule (+5 more)

### Community 10 - "test_generation.py"
Cohesion: 0.14
Nodes (18): GroundedAnswerChunk, LLM provider interface. Phase 3 deliverable. The RAG layer never imports a…, One piece of a streaming response., One source chunk fed to the model, with its provenance., Token counts returned by the provider for budget tracking., SourceMetadata, TokenUsage, FakeLLMProvider (+10 more)

### Community 11 - "vercel.json"
Cohesion: 0.40
Nodes (4): buildCommand, installCommand, outputDirectory, $schema

### Community 12 - "test_permissions.py"
Cohesion: 0.17
Nodes (26): build_predicate_set(), predicates_for(), Assemble the full candidate predicate set: permissions, corpus, then filters., Used by tests and by `dev_headers` mode. Deliberately narrow by default., restricted_principal(), fields(), Permission-aware retrieval. Project_Plan.md Phase 2 exit criterion: "permission…, Project_Plan.md section 0 decides collateral has a single owner. That is a… (+18 more)

### Community 13 - "catalog/models.py"
Cohesion: 0.19
Nodes (28): build_portfolio_graph(), get_neighborhood(), UUID, query_product_impact(), Full integrity audit: cycle detection and contradiction detection., Answers 'what does X require and what does it break' without a human reading a…, Builds a neighborhood subgraph around a single product., Assembles node-link data for the visual graph. (+20 more)

### Community 22 - "retrieval/search.py"
Cohesion: 0.14
Nodes (26): permission_predicate_count(), Hybrid retrieval: pgvector + PostgreSQL full-text search, fused with RRF. Shape…, Used by the regression test that guards the Phase 2 exit criterion., corpus_predicates(), Op, Origin, StrEnum, Retrieval filters, expressed as data. Why an intermediate representation… (+18 more)

### Community 23 - "jobs.py"
Cohesion: 0.20
Nodes (13): job_stats(), JobOut, list_jobs(), BaseModel, get, Session, QueueStatsOut, Per-job status. Every failure is individually explainable and retryable, which… (+5 more)

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
Cohesion: 0.16
Nodes (18): os, py_compile, main(), Graphify automatic update script. Re-extracts AST nodes and edges across code…, run_update(), load_dataset(), Path, Run generation evaluation suite for Phase 3 grounded answers. Project_Plan.md… (+10 more)

### Community 30 - "Graphify Synchronization and Knowledge Graph Navigation"
Cohesion: 0.18
Nodes (10): 1. When to Use, 2. Navigating the Graph (Prompt Trigger), 3. Automatic & Manual Graph Synchronization, 4. Validation, A. Semantic Subgraph Query, B. Shortest Dependency Path, C. Node Explanation, Graphify Synchronization and Knowledge Graph Navigation (+2 more)

### Community 31 - "2. Verification Runbook"
Cohesion: 0.22
Nodes (8): 1. When to Use, 2. Verification Runbook, 3. Verification Checklist Before Concluding, Step 1: Run Unified Project Verification, Step 2: Backend Unit & Integration Tests, Step 3: Frontend Typechecking and Production Build, Step 4: Adding Tests for New Features, Test and Verification Skill

### Community 32 - "Workspace Rules - Personal Knowledge AI"
Cohesion: 0.18
Nodes (8): 1. Graphify Knowledge Graph (Active & Enforced), 2. Test & Verification Guarantee, 3. Security & Scalability Priorities, Workspace Rules - Personal Knowledge AI, 1. Graphify Knowledge Graph (Active & Enforced), 2. Test & Verification Guarantee, 3. Security & Scalability Priorities, Workspace Rules - Personal Knowledge AI

### Community 33 - "seeds.py"
Cohesion: 0.12
Nodes (15): CapabilityIn, ProductCapabilityIn, ProductEdgeIn, ProductIn, Any, field_validator, Session, UUID (+7 more)

### Community 35 - "index.ts"
Cohesion: 0.17
Nodes (16): ChunkInspector(), Props, Props, api, AskResponse, BulkUploadOut, Conversation, ConversationListResponse (+8 more)

### Community 36 - "test_injection.py"
Cohesion: 0.18
Nodes (15): neutralize_fences(), Strip forged delimiters so document text cannot close its own fence. This is…, Fence retrieved content for a prompt. Phase 3 must use this for every source., Flag instruction-like passages. Never blocks ingestion., scan_for_injection(), wrap_untrusted(), The injection corpus. Project_Plan.md Phase 1 exit criterion: "the injection…, A noisy detector gets ignored, which makes it worse than none. (+7 more)

### Community 37 - "extract"
Cohesion: 0.15
Nodes (20): detect_file_type(), extract(), Path, Extract from raw bytes or a path. Bytes are preferred; paths are a convenience., Extension-based type, kept for scripts and tests. The upload path uses…, parametrize, Golden extraction tests: one fixture per format, plus one malformed file per…, Every failure must be a named application error with a readable message, never… (+12 more)

### Community 40 - "test_conversations.py"
Cohesion: 0.16
Nodes (32): Conversation, Message, add_message(), auto_title(), create_conversation(), delete_conversation(), get_conversation(), get_history() (+24 more)

### Community 41 - "PredicateSet"
Cohesion: 0.19
Nodes (7): PermissionFilterMissing, A retrieval query was assembled without its permission predicates. This is a…, assert_enforced(), PredicateSet, The tripwire. An empty or filter-only predicate set must never run., test_removing_the_permission_predicates_fails_loudly(), How the permission filter fails loudly if removed

### Community 42 - "App.tsx"
Cohesion: 0.27
Nodes (6): App(), SearchExplorer(), UploadButton(), useDocuments(), frontend_src_index, react

### Community 43 - "test_graph_integrity.py"
Cohesion: 0.12
Nodes (19): compute_coverage(), detect_contradictions(), detect_cycles_in_requires(), dfs(), Any, Coverage report verifying every product has >= 1 capability, >= 1 document, and…, Detect cycles in directed `requires` edges. An edge (A -> B) with…, Detect logical contradictions in the graph. Contradiction rules: 1. Direct… (+11 more)

### Community 46 - "queue.py"
Cohesion: 0.23
Nodes (19): IngestionJob, JobStatus, Durable ingestion queue. Deviation from the plan, on purpose: FastAPI…, claim(), enqueue(), fail(), _now(), Session (+11 more)

### Community 47 - "CatalogService"
Cohesion: 0.15
Nodes (41): approve_edge(), assign_capability(), audit_graph_coverage(), audit_graph_integrity(), create_capability(), create_edge(), create_product(), create_reference_architecture() (+33 more)

### Community 48 - "sqlalchemy"
Cohesion: 0.07
Nodes (32): argparse, setup_logging(), get_or_create_default_org(), Session, json, pathlib, resource, main() (+24 more)

### Community 49 - "test_safety_limits.py"
Cohesion: 0.11
Nodes (30): ExtractionTimeout, Parsing exceeded its wall-clock budget. Tracked separately: it usually means a…, The file tripped a pre-parse safety limit (zip bomb, entity expansion,…, UnsafeFile, ArchiveReport, check_html_safety(), Deadline, guard_extracted_size() (+22 more)

### Community 50 - "test_integration.py"
Cohesion: 0.14
Nodes (28): DocumentChunk, Organization, Tenant root. Phase 0 will add row-level security keyed on this column; the…, _hydrate(), _ms(), Session, search(), SearchHit (+20 more)

### Community 51 - "jobs/worker.py"
Cohesion: 0.16
Nodes (15): loop(), The single ingestion worker. Runs either inside the API process (a daemon…, Claim and run at most one job. Returns True if work was done., run_once(), start_background_workers(), stop_background_workers(), worker_id(), lifespan() (+7 more)

### Community 52 - "DocumentList.tsx"
Cohesion: 0.38
Nodes (4): DocumentList(), formatSize(), Props, KnowledgeDocument

### Community 53 - "dependencies"
Cohesion: 0.50
Nodes (4): dependencies(), health(), get, Can the backend reach PostgreSQL, pgvector, object storage, and the embedding…

### Community 55 - "documents.py"
Cohesion: 0.06
Nodes (62): _as_http(), delete_document(), document_chunks(), document_status(), _filename_for_url(), get_document(), ingest_paste(), ingest_url() (+54 more)

### Community 56 - "test_rate_limit.py"
Cohesion: 0.14
Nodes (30): GenerationRateLimited, The organization's token budget for this period has been reached., The user has exceeded their per-minute generation rate limit., TokenBudgetExhausted, Per-org, per-month token budget for cost control. Project_Plan.md L195: per-org…, TokenBudget, check_rate_limit(), check_token_budget() (+22 more)

### Community 57 - "reciprocal_rank_fusion"
Cohesion: 0.18
Nodes (19): FusedHit, RankedList, Reciprocal Rank Fusion. Pure, deterministic, and unit-tested without a…, One retrieval branch's output, best first., 1-based rank per id, first occurrence wins., Fuse ranked lists. `score = sum(weight / (k + rank))` over the branches. Ties…, reciprocal_rank_fusion(), branches() (+11 more)

### Community 58 - "test_graph_query.py"
Cohesion: 0.11
Nodes (16): _mock_edge(), _mock_product(), UUID, Phase 4: Graph query tests. Tests the 'what does X require and what does it…, A conflicts_with B → query A yields B as incompatibility., A requires B, B conflicts_with C → query A yields C as indirect conflict., A integrates_with B → query A shows B as integration., A alternative_to B → query A shows B as alternative. (+8 more)

### Community 59 - "db/models.py"
Cohesion: 0.10
Nodes (37): EdgeSuggestionEngine, Session, UUID, Scans document text for implied relationships between catalog products.…, Base, Capability, EvaluationQuestion, Product (+29 more)

### Community 60 - "GroundedChat"
Cohesion: 0.48
Nodes (6): GroundedChat(), handleDelete(), handleSend(), loadConversationDetails(), loadConversations(), loadConversationSources()

### Community 61 - "GeminiLLMProvider"
Cohesion: 0.16
Nodes (10): _detect_refusal(), _extract_cited_indices(), GeminiLLMProvider, _map_citations(), retry, Detect whether the model refused to answer due to insufficient context., Extract unique source indices cited in the answer text., Map cited source indices back to SourceMetadata from context_chunks. (+2 more)

### Community 62 - "test_search_sql.py"
Cohesion: 0.12
Nodes (28): Predicate, _coerce(), compile_predicate(), compile_predicate_set(), Exception, Translate the predicate IR into SQLAlchemy clauses. Thin on purpose. All of the…, AND everything together. The origin of a predicate never affects how it is…, UnknownFilterField (+20 more)

### Community 63 - "pytest"
Cohesion: 0.10
Nodes (24): event_generator(), applied_migrations(), Idempotent, recorded schema migrations. The project had none:…, Apply every unapplied step. Returns the names that ran., run_migrations(), backoff_seconds(), Retry schedule. Pure arithmetic, kept separate so it can be tested without a DB., Exponential backoff with deterministic jitter. Jitter is derived from… (+16 more)

### Community 64 - "EmbeddingProvider"
Cohesion: 0.09
Nodes (13): EmbeddingProvider, ABC, Embed chunk text for indexing., Embed a user question for retrieval., The RAG layer talks to this, never to a vendor SDK directly., get_embedding_provider(), FakeEmbeddingProvider, Deterministic hash-based vectors. For tests and offline development only. (+5 more)

### Community 66 - "_HtmlTextExtractor"
Cohesion: 0.32
Nodes (3): _HtmlTextExtractor, Stdlib parser: tolerant, and it never resolves external entities or DTDs., HTMLParser

### Community 67 - "1. Security Engineering & Auditing"
Cohesion: 0.15
Nodes (12): 1. Security Engineering & Auditing, 2. Scalability & High-Performance Engineering, 3. Architecture Review Checklist, A. Authentication & Authorization, A. High-Scale Vector Search (`pgvector`), B. Database Connection Pooling, B. Input Validation & Injection Defense, C. Asynchronous & Queue-Backed Processing (+4 more)

### Community 71 - "UnsupportedFileType"
Cohesion: 0.17
Nodes (19): UnsupportedFileType, decide_file_type(), normalize_extension(), Decide what a file actually is from its bytes, not from its name.…, Content wins. The declared extension is recorded, never trusted. Raises…, Best-effort content identification of an in-memory upload., sniff(), _sniff_zip() (+11 more)

### Community 72 - "test_generation_adversarial.py"
Cohesion: 0.18
Nodes (10): Adversarial test suite for Phase 3 grounded generation. Project_Plan.md L201:…, Adversarial input attempting to close fences is neutralized., System prompt explicitly forbids guessing on pricing, products, or competitive…, When no sources are retrieved for an adversarial/out-of-domain question,…, Phase 3 architecture constraint: no tool calling or shell execution in…, test_adversarial_prompt_injection_neutralization(), test_fake_llm_refusal_on_empty_context(), test_no_tool_access_in_generation_layer() (+2 more)

### Community 76 - "Phase 1 and Phase 2, as built"
Cohesion: 0.17
Nodes (11): 2. Phase 1: ingestion, 3. Deviation: metadata is not all mandatory at upload, 4. Honest gaps, 5. Phase 2: hybrid retrieval, 6. Running it, 7. What Phase 3 inherits, Changes made on purpose, How "filters before fusion" is guaranteed (+3 more)

### Community 77 - "What is left"
Cohesion: 0.14
Nodes (13): Also included (small, load-bearing extras), Build Status, Known deviations from the plan document, Phase 0 - Project setup, Phase 1 - Document ingestion, Phase 2 - Retrieval (not started), Phase 3 - Grounded generation (not started), Phase 4 - Evaluation (not started) (+5 more)

### Community 78 - "_make_product"
Cohesion: 0.23
Nodes (6): ProductUpdate, ReferenceArchitectureIn, ReferenceArchitectureProductItem, _make_product(), TestProductCRUD, TestReferenceArchitectures

### Community 80 - "Principal"
Cohesion: 0.13
Nodes (24): AccessGrant, Per-account read grant. Consumed by retrieval today, issued by an admin UI in…, Collateral metadata captured at ingest. **Deliberate deviation from…, Permission-aware retrieval. Project_Plan.md Phase 2: "candidates are filtered…, _parse_uuid(), UUID, FastAPI dependency that turns a request into a `Principal`. Isolated from…, resolve_principal() (+16 more)

### Community 81 - "Roadmap: Notes + Grounded AI"
Cohesion: 0.15
Nodes (12): Design rules, Feature parity map, Open decisions, Phase 10: Platform and ecosystem, Phase 6: Notes core, Phase 7: Linking and graph, Phase 8: Notebook studio, Phase 9: Differentiators (+4 more)

### Community 83 - "2. Architectural Components"
Cohesion: 0.25
Nodes (7): 2. Architectural Components, 3. Seed Catalog Summary (20 Products), 4. Exit Criteria Verification, B. Graph Traversal & Integrity Engine (`backend/app/catalog/graph.py`), C. AI Edge Suggestion & Curation Workflow (`backend/app/catalog/curation.py`), D. API Layer (`backend/app/api/routes/catalog.py`), Phase 4: Product Catalog and Typed Graph, as built

### Community 87 - "Phase 3: Grounded Answers, as built"
Cohesion: 0.25
Nodes (7): 1. Overview of Phase 3 Deliverables, 2. Architectural Components, 3. Intentional Changes & Design Decisions, 4. Honest Gaps & Future Work, A. LLM Provider Layer (`app/llm/`), C. API Endpoints (`app/api/routes/ask.py`), Phase 3: Grounded Answers, as built

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

### Community 93 - "llm/gemini.py"
Cohesion: 0.33
Nodes (6): get_logger(), Gemini LLM provider for Phase 3 grounded generation. Uses httpx directly (same…, httpx, Logger, logging, tenacity

### Community 96 - "routes/search.py"
Cohesion: 0.24
Nodes (11): post, Session, Hybrid retrieval with its scores and fusion inputs exposed. This is the Phase 2…, search_endpoint(), BaseModel, The debug endpoint's contract: scores and fusion inputs are always exposed.…, Caller-supplied narrowing. Required, not optional, per Phase 2: every field…, SearchFiltersIn (+3 more)

### Community 98 - "LocalStorage"
Cohesion: 0.36
Nodes (3): LocalStorage, Path, Development-only stand-in for R2. Never use on Render (ephemeral filesystem).

### Community 99 - "config.py"
Cohesion: 0.20
Nodes (6): LLM provider factory. Mirrors the embedding factory pattern: reads…, ObjectStorage, ABC, Original uploaded files live here. PostgreSQL only stores the key., functools, pydantic_settings

### Community 101 - "Block"
Cohesion: 0.10
Nodes (24): Anchor, Citation anchors. A citation is only trustworthy if it resolves to one place in…, Grouping key for chunking: a chunk never spans two anchors., Human-readable citation suffix, e.g. 'p. 12' or 'Pricing!A1:D20'., Chunk, chunk_blocks(), Deterministic, structure-aware chunking. Rules kept intentionally simple until…, _windows() (+16 more)

### Community 104 - "OcrProvider"
Cohesion: 0.15
Nodes (7): OcrProvider, ABC, Optical character recognition for PDFs with no text layer., NullOcrProvider, The default. OCR is off unless someone deliberately turns it on. Reasoning…, pytesseract + Pillow. Optional import: the API starts fine without either., TesseractOcrProvider

### Community 106 - "test_generation_prompts.py"
Cohesion: 0.14
Nodes (19): build_context_block(), build_user_message(), format_history_turn(), format_source(), Versioned prompt templates for Phase 3 grounded generation. Project_Plan.md…, Build the user-turn content: context followed by the question., Format a conversation history turn for the model., Format one retrieved source chunk for the prompt. The `text` parameter is… (+11 more)

### Community 113 - "injection.py"
Cohesion: 0.33
Nodes (4): InjectionFinding, Prompt-injection containment. Project_Plan.md principle 7: "Ingested content is…, re, secrets

### Community 114 - "fixtures.py"
Cohesion: 0.12
Nodes (9): _escape(), make_pdf(), make_pdf_with_javascript(), make_zip_bomb(), Fixture builders for the ingestion tests. Everything is generated at test time…, A valid, minimal, multi-page text PDF. `pages[i]` is the lines of page i+1., An OOXML-shaped package whose members expand far beyond the limit., io (+1 more)

### Community 115 - "generation/service.py"
Cohesion: 0.29
Nodes (11): ask(), ask_stream(), _prepare_context(), Session, UUID, RAG orchestration: retrieval → injection containment → LLM → cited answer. This…, Generate a grounded answer (synchronous). The full pipeline: 1. Rate limit…, Generate a grounded answer with streaming. Yields GroundedAnswerChunk objects.… (+3 more)

### Community 118 - "errors.py"
Cohesion: 0.40
Nodes (4): GenerationRefused, PermissionDenied, The caller's grants do not cover the resource. Surfaced as 404, never 403, so…, The model refused to answer because context was insufficient. This is not an…

### Community 130 - "GroundedAnswer"
Cohesion: 0.40
Nodes (3): GroundedAnswer, A fully grounded answer with structured citations and provenance., test_grounded_answer_includes_conversation_and_message_ids()

### Community 135 - "_build_retrieval_filters"
Cohesion: 0.67
Nodes (3): _build_retrieval_filters(), Convert the generation request filters to retrieval filters., test_build_retrieval_filters()

### Community 141 - "Phase 3 Grounded Generation Baseline"
Cohesion: 0.40
Nodes (4): Adversarial Test Cases, Benchmark Summary, Phase 3 Grounded Generation Baseline, Refusal Test Cases

## Knowledge Gaps
- **152 isolated node(s):** `personal-knowledge-ai-backend`, `name`, `private`, `version`, `type` (+147 more)
  These have ≤1 connection - possible missing edges or undocumented components. (Counts symbols only; 640 node(s) total have ≤1 connection when file, concept and rationale nodes are included.)
- **61 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `Principal` connect `Principal` to `routes/search.py`, `documents/service.py`, `test_permissions.py`, `CatalogService`, `test_integration.py`, `generation/service.py`, `documents.py`, `retrieval/search.py`, `jobs.py`, `ask.py`?**
  _High betweenness centrality (0.055) - this node is a cross-community bridge._
- **Why does `Settings` connect `Settings` to `config.py`, `1. Security Engineering & Auditing`?**
  _High betweenness centrality (0.046) - this node is a cross-community bridge._
- **Why does `Document` connect `documents/service.py` to `seeds.py`, `catalog/models.py`, `What is left`, `CatalogService`, `Principal`, `sqlalchemy`, `test_integration.py`, `jobs/worker.py`, `retrieval/search.py`, `documents.py`, `db/models.py`, `test_search_sql.py`?**
  _High betweenness centrality (0.044) - this node is a cross-community bridge._
- **Are the 52 inferred relationships involving `CatalogService` (e.g. with `approve_edge()` and `assign_capability()`) actually correct?**
  _`CatalogService` has 52 INFERRED edges - model-reasoned connections that need verification._
- **Are the 36 inferred relationships involving `Principal` (e.g. with `ask_endpoint()` and `ask_in_conversation_endpoint()`) actually correct?**
  _`Principal` has 36 INFERRED edges - model-reasoned connections that need verification._
- **Are the 30 inferred relationships involving `Document` (e.g. with `get_product()` and `get_document()`) actually correct?**
  _`Document` has 30 INFERRED edges - model-reasoned connections that need verification._
- **Are the 16 inferred relationships involving `ProductEdge` (e.g. with `EdgeSuggestionEngine` and `build_portfolio_graph()`) actually correct?**
  _`ProductEdge` has 16 INFERRED edges - model-reasoned connections that need verification._