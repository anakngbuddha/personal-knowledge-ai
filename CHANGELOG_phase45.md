# Phase 4.1 + Phase 5

## Phase 4.1: Customer Brief
- LLM extraction (Claude) of structured requirements from pasted/uploaded briefs
- Regex fallback validates budget ($50k, 100k budget) and seat counts (50 users, 5 rooms)
- BriefCard React component: editable inline in Ask conversation (grid + lists + save/cancel)
- 5 API endpoints: extract, extract/file, save-as-note, chat-card, update field
- Generation service: generate_with_brief() constrains answers by brief, generate_with_advisor_context() for playbooks

### Key Decisions
- LLM output: JSON-only, null for unknowns, arrays for lists
- Chat card always editable, all fields modifiable, changes trigger re-fetch
- Brief stored as markdown Note (type=BRIEF) with brief_id reference
- Brief context injected into generation prompts

## Phase 5: Navigation Rewrite + Three-Pane Ask
- Collapsible sidebar nav (Notebooks, Playbooks, Maps, Sources) with badges
- Three-pane Ask: sources (left, multi-select) | chat (center, mixed content) | product map (right, nodes+edges)
- Brief card embeds in chat as rich editable component
- Source selection filters product map and passage retrieval
- Product graph: 2-hop expansion, max 6 neighbors per node

### Files
- backend/app/playbooks/brief.py (new)
- backend/app/playbooks/brief_api.py (new)
- backend/app/generation/service.py (updated)
- frontend/components/BriefCard.tsx (new)
- frontend/components/Navigation.tsx (new)
- frontend/components/ThreePaneAsk.tsx (new)

### Remaining
- 4.2: Advisor Playbook (bundles, Word/PPT export)
- 4.3: Notes UI (markdown, wikilinks, backlinks, graph)
- 4.4: Notebooks (named workspaces, scoping)
- 4.5: NotebookLM helpers (summaries, Q&A, FAQ, compare)
- 6: Evals, Gemini rate limiter, job resume, USER_GUIDE
