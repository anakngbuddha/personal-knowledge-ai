---
name: graphify-sync
description: >-
  Use this skill to navigate the codebase knowledge graph, execute Graphify queries on user prompts,
  and keep the graph synchronized automatically whenever files in the codebase are modified.
---

# Graphify Synchronization and Knowledge Graph Navigation

This skill guides the agent in using Graphify to understand codebase architecture, query relationships, and keep the knowledge graph up to date.

## 1. When to Use
- **On every incoming prompt**: When understanding user intent, finding relevant modules, or discovering symbols across the project.
- **Before making architectural changes**: To see what callers and dependencies will be impacted.
- **After every file modification**: To re-extract AST nodes and synchronize connections in `graphify-out/`.

## 2. Navigating the Graph (Prompt Trigger)

Instead of running slow directory greps or reading dozens of files into context, query the local Graphify knowledge graph:

### A. Semantic Subgraph Query
Search for specific concepts, functions, or architectural domains:
```bash
python -m graphify query "<your question or symbol>"
```
Example:
```bash
python -m graphify query "how does document chunking connect to embedding storage?"
```

### B. Shortest Dependency Path
Discover how two disparate modules or classes interact:
```bash
python -m graphify path "<source_node>" "<target_node>"
```
Example:
```bash
python -m graphify path "chunk_blocks" "pgvector"
```

### C. Node Explanation
Inspect a specific symbol, module, or database model, its docstrings, callers, and callees:
```bash
python -m graphify explain "<symbol_name>"
```
Example:
```bash
python -m graphify explain "chunk_blocks"
```

## 3. Automatic & Manual Graph Synchronization

Whenever any code file is added, edited, or deleted, update the graph:

### Quick AST Update (0 API Cost, ~1s runtime)
```bash
python -m graphify update .
```
Or use the workspace script:
```bash
python scripts/graphify_update.py
```

### What gets updated:
1. `graphify-out/graph.json`: Machine-readable graph of all nodes, edges, and communities.
2. `graphify-out/graph.html`: Visual interactive graph for browser inspection.
3. `graphify-out/GRAPH_REPORT.md`: Plain-English report detailing god nodes, clusters, and architectural insights.

## 4. Validation
Verify the graph after update:
```bash
python -c "import json; d=json.load(open('graphify-out/graph.json')); print(f'Nodes: {len(d[\"nodes\"])}, Edges: {len(d[\"edges\"])}')"
```
If the node count reflects recent file edits, synchronization is successful.
