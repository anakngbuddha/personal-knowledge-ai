# Graph Report - personal-knowledge-ai  (2026-09-19)

## Corpus Check
- 70 files · ~12,522 words
- Verdict: corpus is large enough that graph structure adds value.
- Unclassified: 5 file(s) not represented in the graph (top: .example 2, (none) 2, .css 1)

## Summary
- 411 nodes · 671 edges · 35 communities (20 shown, 15 thin omitted)
- Extraction: 95% EXTRACTED · 5% INFERRED · 0% AMBIGUOUS · INFERRED: 31 edges (avg confidence: 0.95)
- Token cost: 0 input · 0 output

## Graph Freshness
- Built from commit: `4cc3b744`
- Run `git rev-parse HEAD` and compare to check if the graph is stale.
- Run `graphify update .` after code changes (no API cost).

## Community Hubs (Navigation)
- service.py
- extraction.py
- StorageError
- App.tsx
- package.json
- Personal Knowledge AI Workspace
- errors.py
- documents.py
- Settings
- compilerOptions
- LLMProvider
- vercel.json
- run_eval.py
- seed_eval_set.py
- personal-knowledge-ai-backend
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
- `1. Security First Principles` --references--> `Settings`  [INFERRED]
  .agents/rules/security-and-scalability.md → backend/app/core/config.py
- `C. Secrets & Environment Isolation` --references--> `Settings`  [INFERRED]
  .agents/skills/security-and-scalability/SKILL.md → backend/app/core/config.py
- `Deliberate decisions` --references--> `ProviderRateLimited`  [INFERRED]
  docs/architecture.md → backend/app/core/errors.py
- `Phase 1 - Document ingestion` --references--> `Document`  [EXTRACTED]
  STATUS.md → backend/app/db/models.py
- `main()` --uses--> `Base`  [INFERRED]
  scripts/init_db.py → backend/app/db/models.py

## Import Cycles
- None detected.

## Communities (35 total, 15 thin omitted)

### Community 0 - "service.py"
Cohesion: 0.08
Nodes (43): dependencies(), health(), get, Phase 0 exit check: can the backend reach PostgreSQL, pgvector, R2, and Gemini?, get_logger(), setup_logging(), Base, Conversation (+35 more)

### Community 1 - "extraction.py"
Cohesion: 0.15
Nodes (28): ExtractionError, UnsupportedFileType, Chunk, chunk_blocks(), Deterministic, structure-aware chunking. Rules kept intentionally simple until…, _windows(), Block, detect_file_type() (+20 more)

### Community 2 - "StorageError"
Cohesion: 0.12
Nodes (12): StorageError, ObjectStorage, ABC, Original uploaded files live here. PostgreSQL only stores the key., LocalStorage, Path, Development-only stand-in for R2. Never use on Render (ephemeral filesystem)., R2Storage (+4 more)

### Community 3 - "App.tsx"
Cohesion: 0.14
Nodes (16): App(), ChunkInspector(), Props, DocumentList(), formatSize(), Props, Props, UploadButton() (+8 more)

### Community 4 - "package.json"
Cohesion: 0.09
Nodes (22): dependencies, react, react-dom, devDependencies, @types/react, @types/react-dom, typescript, vite (+14 more)

### Community 5 - "Personal Knowledge AI Workspace"
Cohesion: 0.08
Nodes (23): Deploy, Design rules this repo actually follows, Ingest a file without the UI, Personal Knowledge AI Workspace, Repository layout, Run it locally, Stack, Tests (+15 more)

### Community 6 - "errors.py"
Cohesion: 0.06
Nodes (27): AppError, ProviderError, ProviderRateLimited, External inference provider failed (network, 5xx, bad payload)., Base application error., Provider returned 429. Tracked separately from retrieval failures., EmbeddingProvider, ABC (+19 more)

### Community 7 - "documents.py"
Cohesion: 0.16
Nodes (23): delete_document(), document_chunks(), document_status(), _get_document(), list_documents(), process_document(), get, Session (+15 more)

### Community 8 - "Settings"
Cohesion: 0.09
Nodes (19): 1. Security First Principles, 2. Scalability & High-Performance Engineering, Security & Scalability Architecture Rules, 1. Security Engineering & Auditing, 2. Scalability & High-Performance Engineering, 3. Architecture Review Checklist, A. Authentication & Authorization, A. High-Scale Vector Search (`pgvector`) (+11 more)

### Community 9 - "compilerOptions"
Cohesion: 0.14
Nodes (13): compilerOptions, isolatedModules, jsx, lib, module, moduleResolution, noEmit, resolveJsonModule (+5 more)

### Community 10 - "LLMProvider"
Cohesion: 0.32
Nodes (5): GroundedAnswer, LLMProvider, ABC, Phase 3 lands here. The interface exists now so the RAG layer never imports a…, dataclasses

### Community 11 - "vercel.json"
Cohesion: 0.40
Nodes (4): buildCommand, installCommand, outputDirectory, $schema

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
Cohesion: 0.14
Nodes (21): json, os, pathlib, py_compile, get_graph_stats(), main(), Path, Graphify PreInvocation hook script. Executed by Antigravity prior to model… (+13 more)

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

## Knowledge Gaps
- **104 isolated node(s):** `personal-knowledge-ai-backend`, `name`, `private`, `version`, `type` (+99 more)
  These have ≤1 connection - possible missing edges or undocumented components. (Counts symbols only; 206 node(s) total have ≤1 connection when file, concept and rationale nodes are included.)
- **15 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `Document` connect `service.py` to `Personal Knowledge AI Workspace`, `documents.py`?**
  _High betweenness centrality (0.078) - this node is a cross-community bridge._
- **Why does `Phase 1 - Document ingestion` connect `Personal Knowledge AI Workspace` to `service.py`?**
  _High betweenness centrality (0.070) - this node is a cross-community bridge._
- **Are the 3 inferred relationships involving `StorageError` (e.g. with `upload_document()` and `LocalStorage`) actually correct?**
  _`StorageError` has 3 INFERRED edges - model-reasoned connections that need verification._
- **Are the 6 inferred relationships involving `Document` (e.g. with `_get_document()` and `list_documents()`) actually correct?**
  _`Document` has 6 INFERRED edges - model-reasoned connections that need verification._
- **Are the 2 inferred relationships involving `process_document()` (e.g. with `Document` and `DocumentStatus`) actually correct?**
  _`process_document()` has 2 INFERRED edges - model-reasoned connections that need verification._
- **What connects `personal-knowledge-ai-backend`, `name`, `private` to the rest of the system?**
  _104 weakly-connected nodes found - possible documentation gaps or missing edges._
- **Should `service.py` be split into smaller, more focused modules?**
  _Cohesion score 0.07764876632801161 - nodes in this community are weakly interconnected._