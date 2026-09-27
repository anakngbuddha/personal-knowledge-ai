# Roadmap

Updated 2026-09-27. The earlier roadmap listed Phases 2-10 as future work; most of that has shipped.
Current state lives in [STATUS.md](STATUS.md). This file tracks only what is **not** done.

## Partial (finish first)

1. **Live quality baseline**: versioned live Gemini + PostgreSQL run (claim support, refusal, citation precision, retrieval Hit@K at production `TOP_K=8`) with representative case counts; then gate releases on it.
2. **RLS enforcement gate**: `RLS_DEFAULT_DENY=true` is configured. Verify the staging database role is non-superuser/NOBYPASSRLS and the app works, then set `RLS_REQUIRED=true`.
3. **Tool-enabled streaming**: stream the final generation after tool execution.
4. **MCP child sandbox**: configure `MCP_CHILD_SANDBOX_COMMAND` in production.
5. **Handler idempotency**: confirm `process_document` and workflow handlers are safe to re-run after a crash.

## Proposed (not established in code)

- Embeds/transclusion (`![[note]]`)
- Audio/YouTube transcription sources, audio overview
- Cited writing, source-to-note distillation, contradiction/gap finder, note claim coverage, cited flashcards, knowledge timeline
- Obsidian vault import/export, desktop wrapper, real-time collaboration
- Reranker or dedicated vector infrastructure, only after a measured ceiling
