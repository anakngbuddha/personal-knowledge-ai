---
trigger: always_on
description: Always consult Graphify on every prompt and auto-update the knowledge graph on all codebase changes.
---

# Graphify Knowledge Graph Rules

The project maintains an active Graphify knowledge graph under `graphify-out/`.

## 1. Prompt-Level Graphify Trigger (Every Prompt)
- **Every prompt triggers Graphify consultation**: Before planning, reading random raw files, or generating modifications, always inspect or query the Graphify knowledge graph (`graphify-out/graph.json` or via CLI).
- For conceptual queries and dependency discovery, run:
  - `python -m graphify query "<topic or question>"` (scoped subgraph BFS traversal)
  - `python -m graphify path "<source_node>" "<target_node>"` (shortest architectural path)
  - `python -m graphify explain "<symbol_or_module>"` (node explanation with caller/callee context)
- If `graphify-out/wiki/index.md` exists, navigate the wiki structure rather than performing broad grep searches.
- Read `graphify-out/GRAPH_REPORT.md` for high-level architectural overviews and god-node distributions.

## 2. Automatic Graph Synchronization (Every Codebase Change)
- **Automatic update on code modifications**: Whenever files are created, updated, or removed, the knowledge graph must be updated immediately so nodes, symbols, and connections reflect reality.
- The lifecycle hook in `.agents/hooks.json` automatically triggers `python scripts/graphify_update.py --hook` on file edits.
- If editing files manually or running batch refactors, explicitly run:
  ```bash
  python -m graphify update .
  ```
  This is AST-only, takes ~1-2 seconds, and incurs zero API token costs.
- Verify `graphify-out/graph.json` has updated node and edge definitions before concluding the task.
