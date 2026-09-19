# Roadmap: Notes + Grounded AI

Status: **proposed**, 2026-09-19. Not thorough on purpose; each phase gets detailed when it starts.
Phases 0-5 are unchanged from `STATUS.md`. Phases 6-10 are new.

## Vision

Obsidian's linked, durable notes combined with NotebookLM's source-grounded AI, built on one idea:
**notes and sources are the same kind of thing.** Both are chunked, embedded, full-text indexed,
linkable, and citable. That single decision is what lets the niche features below exist.

## Design rules

Existing rules stay (smallest useful slice, citation metadata at ingestion, one database until
measured, provider interfaces, retrieval measured against a labeled set). Added:

6. **Notes are sources.** Notes go through the same chunk/embed/index pipeline as uploads.
7. **AI proposes, the human decides.** The AI never silently edits or links a note. Suggestions
   go to an accept/reject queue.
8. **Markdown is the portable format.** Nothing traps the user's data; import/export is a feature.

## Phase overview

| Phase | Name | Theme | State |
|---|---|---|---|
| 0 | Project setup | V1 | Done |
| 1 | Document ingestion | V1 | Done |
| 2 | Hybrid retrieval | V1 | Next |
| 3 | Grounded generation + citations | V1 (NotebookLM core) | Not started |
| 4 | Evaluation baseline | V1 | Not started |
| 5 | Chat + citation UI | V1 close-out | Partially standing |
| 6 | Notes core | V2 (Obsidian foundation) | Not started |
| 7 | Linking and graph | V2 (Obsidian parity) | Not started |
| 8 | Notebook studio | V3 (NotebookLM parity) | Not started |
| 9 | Differentiators | V4 (niche) | Not started |
| 10 | Platform and ecosystem | V5 | Not started |

Do not start a phase until the previous one meets its exit criteria.

---

## V1: Grounded Q&A (Phases 0-5)

See `STATUS.md` for task-level detail. Summary: upload docs, hybrid search (vector + FTS + RRF),
answer with citations, measure it, and show it in a usable chat UI. V1 is the NotebookLM-style
engine that everything else sits on.

---

## Phase 6: Notes core

Goal: write and organize notes in the app, and make them searchable and citable like any source.

- Markdown editor with live preview (see open decisions)
- `notes` table: title, Markdown body, timestamps
- `note_versions` table: snapshot on save. Cheap now, and it enables the timeline feature in Phase 9
- Folders and tags; YAML frontmatter parsed into properties
- Notes run through the existing ingestion path (chunk, embed, tsvector) so chat can cite them
- Full-text + semantic search across notes and documents together
- Reindex on save (debounced), never on every keystroke

**Exit:** write a note, ask a question in chat, get an answer that cites the note by heading.

## Phase 7: Linking and graph

Goal: the connective tissue that makes Obsidian feel like Obsidian.

- `[[wikilinks]]`, `[[note#heading]]`, aliases, autocomplete, rename-safe links
- `links` table extracted on save; backlinks panel; unlinked-mentions panel
- Graph view (global and local neighborhood) with tag/folder filters
- Daily notes, templates, quick switcher / command palette
- Embeds/transclusion (`![[note]]`), if time allows

**Exit:** rename a note and no link breaks; the graph reflects real links.

## Phase 8: Notebook studio

Goal: NotebookLM parity, applied to your notes and documents together.

- **Notebooks**: named source sets used as a retrieval scope; toggle sources on and off per chat
- Auto "source guide" per source: summary, key topics, suggested questions
- Generated outputs, all cited: briefing doc, study guide, FAQ, timeline
- Save any answer as a note (with its citations intact)
- More ingestion: web URL, pasted text, OCR for scans
- Stretch: audio overview

**Exit:** pick a notebook of 5+ mixed sources and get a cited briefing doc from it.

## Phase 9: Differentiators

The niche layer. None of these exist in either product; all depend on notes-as-sources.
Each is optional and ordered roughly by value over effort. Build one at a time and evaluate it.

| # | Feature | What it does | Needs |
|---|---|---|---|
| 1 | **Graph-aware retrieval** | Expand retrieval through links and backlinks; scope questions to a folder, tag, or link neighborhood. | 2, 7 |
| 2 | **Cited writing** | While drafting, "find support" pulls passages from your own sources and inserts a citation link. AI-drafted text carries provenance. | 3, 6 |
| 3 | **Source-to-note distillation** | Select a passage in a PDF, get an atomic note with a page-cited backlink (literature-note workflow). | 6, 7 |
| 4 | **Suggested links with reasons** | AI proposes links between notes and explains why; accept/reject queue. | 7 |
| 5 | **Contradiction and gap finder** | Flags notes/sources that disagree, and concepts mentioned often but with no note. | 8 |
| 6 | **Claim coverage** | For a note, show which claims are backed by your sources and which are unsupported. | 3, 6 |
| 7 | **Cited flashcards** | Auto-generate spaced-repetition cards whose answers link to the source passage. | 6 |
| 8 | **Knowledge timeline** | "What did I know about X on this date?" from note version history. | 6 |

**Exit:** each shipped feature has a written before/after check, not just a demo.

## Phase 10: Platform and ecosystem

- Obsidian vault import/export (Markdown, frontmatter, wikilinks, attachments)
- Desktop wrapper (Tauri) and/or PWA with offline reading and editing
- Auth, multi-user, sharing, real-time collaboration (only if wanted)
- Sync strategy if a local-first mode is adopted
- Plugin/API surface
- Reranker or dedicated infrastructure **only** if evaluation hits a measured ceiling

---

## Feature parity map

| Feature | From | Phase |
|---|---|---|
| Cited answers over your sources | NotebookLM | 3 |
| Chat history, clickable citations | NotebookLM | 5 |
| Markdown notes, folders, tags | Obsidian | 6 |
| Wikilinks, backlinks, graph view | Obsidian | 7 |
| Daily notes, templates, command palette | Obsidian | 7 |
| Notebooks / source toggling | NotebookLM | 8 |
| Source guide, briefing, study guide, FAQ | NotebookLM | 8 |
| URL / pasted text / OCR sources | NotebookLM | 8 |
| Vault compatibility, desktop app | Obsidian | 10 |
| Niche features (graph-aware retrieval, etc.) | New | 9 |

## Open decisions

None of these block Phases 2-5. Decide before Phase 6 starts.

| Decision | Proposed default | Alternative | Why it matters |
|---|---|---|---|
| Platform | Stay web (current stack) | Tauri desktop app in Phase 10 | Keeps V1 work; a wrapper can come later |
| Source of truth for notes | Postgres rows holding Markdown | Markdown files on disk (Obsidian-style vault) | Files-first fits Obsidian better but conflicts with the Render/R2 deployment. Vault import/export in Phase 10 bridges the gap |
| Editor | CodeMirror 6 (Markdown source with live-preview styling) | TipTap (WYSIWYG) | Obsidian-like feel vs. easier rich editing |
| Auth | Single user until Phase 10 | Add accounts earlier | Avoids retrofitting workspaces later; `workspace_id` already exists in storage keys |