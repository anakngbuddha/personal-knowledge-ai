# PART2 Phase 4.3 - Notes UI: Obsidian-style markdown editor with wikilinks and graph

**Status: shipped.** Backend API, frontend editor component, and tests are on `main`.
No new dependencies. No new environment variables.

## What it does

Phase 4.3 completes the advisor flow started in Phase 4.1 (brief) and 4.2 (recommendation):
users can now **save answers and create notes** with a live markdown editor, **link notes to products and other notes** with `[[wikilinks]]`, see **backlinks** (what links to this note), and visualize the note/product/account graph.

## Files

| File | What it is |
|---|---|
| `backend/app/api/routes/notes.py` | Extended with `/notes/graph`, `/notes/link-targets`, `/notes/from-answer`, backlinks. |
| `frontend/src/components/NotesEditor.tsx` | Three-pane layout: notes list, editor, and tab views (editor/graph/backlinks). |
| `frontend/src/components/NotesEditor.css` | Styling for the Notes UI. |
| `backend/tests/test_notes_phase43.py` | 15+ tests for wikilinks, graph, backlinks, auto-title. |

## Features

### Backend

1. **Graph endpoint** (`GET /notes/graph`) — returns all notes and products as nodes, wikilinks as edges for visualization.
2. **Link targets autocomplete** (`GET /notes/link-targets?q=...`) — suggests products and notes when user types `[[`.
3. **Save answer as note** (`POST /notes/from-answer`) — accepts a message_id from chat or raw text, auto-generates title, saves as a note.
4. **Backlinks** (`GET /notes/{id}/backlinks`) — returns all notes that link to a given note (or product/account by kind/ref).
5. **Wikilink parsing** — extracts and resolves `[[product:name]]`, `[[note:slug]]`, `[[account:name]]`, with optional `|alias`.

### Frontend

1. **Live markdown editor** with title and body, auto-save on blur.
2. **Wikilink autocomplete** — detects `[[` and suggests products/notes; user types and selects.
3. **Three view modes**:
   - **Editor**: full markdown editor with wikilinks
   - **Graph**: visual representation of notes, products, and their connections
   - **Backlinks**: all notes that reference this note
4. **Notes sidebar** — list of all notes, quick access, filtering via search.
5. **Save from chat** — "Save this answer as a note" button on chat messages (integration point for UI teams).

## Rules and design decisions

* **Notes are embedded on save.** Already implemented in Phase 4.1; notes become searchable immediately.
* **Wikilinks to sources are parsed at read time, not stored.** Per CHANGELOG_phase42, documents change and a stored link would go stale. Prefix-less links like `[[firewall-plus]]` resolve to product first, then note.
* **Only resolved links appear in the graph.** Unresolved links (target does not exist) are stored but not rendered, keeping the visualization clean.
* **Account links are string refs** (no CRM backend yet), so `[[account:acme-corp]]` always resolves.
* **Graph is simple force-directed layout.** For large workspaces (500+ nodes), this may be slow; a real implementation would use D3 or similar.
* **Auto-title is deterministic.** Strips markdown, takes the first line, caps at 80 chars.

## Endpoints

| Method | Path | Purpose |
|---|---|---|
| GET | `/notes/graph` | Nodes (notes, products, accounts) + edges (wikilinks). |
| GET | `/notes/link-targets?q=...` | Autocomplete for wikilink targets. |
| POST | `/notes/from-answer` | Save a chat message or text as a note. |
| GET | `/notes/{id}/backlinks` | Notes that link to this note. |
| GET | `/notes/by-link/{kind}/{ref}` | Alternative backlinks query (already existed). |

## Frontend integration points

1. **In the Ask tab**: add a "Save as note" button on answer messages that calls `POST /notes/from-answer` with the message_id.
2. **In the navigation**: replace "Tribal Ledger" with "Notes" in the tab bar (part of Phase 5.1, but noted here for clarity).
3. **Link insertion**: when user types `[[` in any markdown editor, show the autocomplete from `/notes/link-targets`.

## Testing

- 15+ offline tests covering wikilinks parsing, note creation with links, graph resolution, backlinks, auto-title.
- No database required for wikilink tests (pure parsing).
- Mock fixtures included for note/product creation tests.

## Acceptance criteria (from PART2)

- [x] Live markdown editor with wikilinks support
- [x] Backlinks panel shows what links to this note
- [x] Graph view combining notes, sources, products
- [x] "Save this answer as a note" from chat (endpoint ready, UI button is Phase 5.1)
- [x] Wikilinks to products/accounts resolve and are rendered
- [x] Notes are embedded on save and retrievable by Ask
- [x] Source links (documents) are parsed at read time, not stored (prevents stale references)

## Handover for Phase 4.4 (Notebooks) and Phase 5 (UX rewrite)

**Phase 4.4** (still outstanding) scopes sources and notes to named notebooks/projects per customer or deal. The Notes UI in 4.3 works at the workspace level; 4.4 will add a notebook picker and filter notes/sources accordingly.

**Phase 5.1** replaces the numbered navigation (01-08) with plain tabs: Sources | Ask | Notes | Map | Connections | Settings. The Notes tab will then be the main entry point to this editor.

**Phase 5.2** adds a three-pane Ask layout with sources on the left (toggleable), chat center, citations/outputs right. This is where the "Save as note" button will live.

## Known limitations

1. **Graph rendering is basic.** Uses an SVG grid layout, not force-directed physics. For workspaces with 100+ notes/products, consider a D3/Cytoscape upgrade.
2. **Wikilink UI is text-based.** No drag-and-drop or visual link builder; users must type `[[product:name]]` or use autocomplete.
3. **No version history.** Notes are not versioned; edits overwrite. A real notebook would track changes.
4. **Backlinks are one-way.** Shows "what links to me" but not "what do I link to" in a separate panel. Could be added as a toggle.

---

# Deployment notes

- No new migrations required.
- No new environment variables.
- `NotesEditor.tsx` uses `@tanstack/react-query` (already in dependencies).
- CSS is scoped to `.notes-editor` class; add to your app's main layout or import on the Notes tab.
- API routes assume the same `resolve_principal` and workspace isolation as existing routes.

# Next steps

1. **Phase 4.4**: Add notebook scoping (workspace → notebooks → notes/sources).
2. **Phase 5.1**: Replace numbered navigation with Sources | Ask | Notes | Map | Connections | Settings.
3. **Phase 5.2**: Three-pane Ask layout with sources sidebar and "Save as note" button.
4. **Phase 6**: Evals and performance (e.g., optimize graph rendering for large workspaces).
