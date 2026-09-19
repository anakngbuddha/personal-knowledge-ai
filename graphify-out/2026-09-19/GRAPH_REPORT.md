# Graph Report - personal-knowledge-ai  (2026-09-19)

## Corpus Check
- 62 files · ~9,851 words
- Verdict: corpus is large enough that graph structure adds value.
- Unclassified: 5 file(s) not represented in the graph (top: .example 2, (none) 2, .css 1)

## Summary
- 359 nodes · 624 edges · 30 communities (15 shown, 15 thin omitted)
- Extraction: 95% EXTRACTED · 5% INFERRED · 0% AMBIGUOUS · INFERRED: 29 edges (avg confidence: 0.95)
- Token cost: 0 input · 0 output

## Graph Freshness
- Built from commit: `4cc3b744`
- Run `git rev-parse HEAD` and compare to check if the graph is stale.
- Run `graphify update .` after code changes (no API cost).

## Community Hubs (Navigation)
- service.py
- extraction.py
- config.py
- App.tsx
- package.json
- Personal Knowledge AI Workspace
- EmbeddingProvider
- documents.py
- main.py
- compilerOptions
- Block
- vercel.json
- run_eval.py
- seed_eval_set.py
- personal-knowledge-ai-backend
- Roadmap: Notes + Grounded AI
- Evaluation Strategy (Phase 4)
- rules/graphify.md
- workflows/graphify.md
- verify_project.py

## God Nodes (most connected - your core abstractions)
1. `EmbeddingProvider` - 13 edges
2. `StorageError` - 12 edges
3. `Document` - 12 edges
4. `Block` - 12 edges
5. `process_document()` - 12 edges
6. `GeminiEmbeddingProvider` - 12 edges
7. `ObjectStorage` - 12 edges
8. `compilerOptions` - 12 edges
9. `Roadmap: Notes + Grounded AI` - 12 edges
10. `_get_document()` - 11 edges

## Surprising Connections (you probably didn't know these)
- `Deliberate decisions` --references--> `ProviderRateLimited`  [INFERRED]
  docs/architecture.md → backend/app/core/errors.py
- `Phase 1 - Document ingestion` --references--> `Document`  [EXTRACTED]
  STATUS.md → backend/app/db/models.py
- `main()` --uses--> `Document`  [INFERRED]
  scripts/ingest_local.py → backend/app/db/models.py
- `main()` --uses--> `Base`  [INFERRED]
  scripts/init_db.py → backend/app/db/models.py
- `upload_document()` --uses--> `StorageError`  [INFERRED]
  backend/app/api/routes/documents.py → backend/app/core/errors.py

## Import Cycles
- None detected.

## Communities (30 total, 15 thin omitted)

### Community 0 - "service.py"
Cohesion: 0.09
Nodes (33): dependencies(), health(), get, Phase 0 exit check: can the backend reach PostgreSQL, pgvector, R2, and Gemini?, Base, Conversation, DocumentChunk, EvaluationQuestion (+25 more)

### Community 1 - "extraction.py"
Cohesion: 0.21
Nodes (20): AppError, ExtractionError, Base application error., UnsupportedFileType, detect_file_type(), extract(), _extract_docx(), _extract_pdf() (+12 more)

### Community 2 - "config.py"
Cohesion: 0.09
Nodes (17): get_settings(), All runtime configuration. Nothing model- or provider-specific is hard-coded., Settings, StorageError, ObjectStorage, ABC, Original uploaded files live here. PostgreSQL only stores the key., LocalStorage (+9 more)

### Community 3 - "App.tsx"
Cohesion: 0.15
Nodes (15): App(), ChunkInspector(), Props, DocumentList(), formatSize(), Props, Props, UploadButton() (+7 more)

### Community 4 - "package.json"
Cohesion: 0.08
Nodes (23): dependencies, react, react-dom, devDependencies, @types/react, @types/react-dom, typescript, vite (+15 more)

### Community 5 - "Personal Knowledge AI Workspace"
Cohesion: 0.08
Nodes (23): Deploy, Design rules this repo actually follows, Ingest a file without the UI, Personal Knowledge AI Workspace, Repository layout, Run it locally, Stack, Tests (+15 more)

### Community 6 - "EmbeddingProvider"
Cohesion: 0.06
Nodes (24): ProviderError, ProviderRateLimited, External inference provider failed (network, 5xx, bad payload)., Provider returned 429. Tracked separately from retrieval failures., EmbeddingProvider, ABC, Embed chunk text for indexing., Embed a user question for retrieval. (+16 more)

### Community 7 - "documents.py"
Cohesion: 0.17
Nodes (25): delete_document(), document_chunks(), document_status(), _get_document(), list_documents(), process_document(), get, Session (+17 more)

### Community 8 - "main.py"
Cohesion: 0.22
Nodes (7): get_logger(), setup_logging(), get, root(), fastapi, fastapi_middleware_cors, Logger

### Community 9 - "compilerOptions"
Cohesion: 0.14
Nodes (13): compilerOptions, isolatedModules, jsx, lib, module, moduleResolution, noEmit, resolveJsonModule (+5 more)

### Community 10 - "Block"
Cohesion: 0.17
Nodes (16): Chunk, chunk_blocks(), Deterministic, structure-aware chunking. Rules kept intentionally simple until…, _windows(), Block, A structural unit of source text (a page, paragraph, or section body)., GroundedAnswer, LLMProvider (+8 more)

### Community 11 - "vercel.json"
Cohesion: 0.40
Nodes (4): buildCommand, installCommand, outputDirectory, $schema

### Community 24 - "Roadmap: Notes + Grounded AI"
Cohesion: 0.15
Nodes (12): Design rules, Feature parity map, Open decisions, Phase 10: Platform and ecosystem, Phase 6: Notes core, Phase 7: Linking and graph, Phase 8: Notebook studio, Phase 9: Differentiators (+4 more)

### Community 25 - "Evaluation Strategy (Phase 4)"
Cohesion: 0.40
Nodes (4): Evaluation Strategy (Phase 4), Experiments, Labeled set, Metrics

### Community 29 - "verify_project.py"
Cohesion: 0.14
Nodes (21): json, os, pathlib, py_compile, get_graph_stats(), main(), Path, Graphify PreInvocation hook script. Executed by Antigravity prior to model… (+13 more)

## Knowledge Gaps
- **74 isolated node(s):** `personal-knowledge-ai-backend`, `name`, `private`, `version`, `type` (+69 more)
  These have ≤1 connection - possible missing edges or undocumented components. (Counts symbols only; 169 node(s) total have ≤1 connection when file, concept and rationale nodes are included.)
- **15 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `Document` connect `documents.py` to `service.py`, `Personal Knowledge AI Workspace`?**
  _High betweenness centrality (0.095) - this node is a cross-community bridge._
- **Why does `Phase 1 - Document ingestion` connect `Personal Knowledge AI Workspace` to `documents.py`?**
  _High betweenness centrality (0.085) - this node is a cross-community bridge._
- **Are the 3 inferred relationships involving `StorageError` (e.g. with `upload_document()` and `LocalStorage`) actually correct?**
  _`StorageError` has 3 INFERRED edges - model-reasoned connections that need verification._
- **Are the 6 inferred relationships involving `Document` (e.g. with `_get_document()` and `list_documents()`) actually correct?**
  _`Document` has 6 INFERRED edges - model-reasoned connections that need verification._
- **Are the 2 inferred relationships involving `process_document()` (e.g. with `Document` and `DocumentStatus`) actually correct?**
  _`process_document()` has 2 INFERRED edges - model-reasoned connections that need verification._
- **What connects `personal-knowledge-ai-backend`, `name`, `private` to the rest of the system?**
  _74 weakly-connected nodes found - possible documentation gaps or missing edges._
- **Should `service.py` be split into smaller, more focused modules?**
  _Cohesion score 0.09358974358974359 - nodes in this community are weakly interconnected._