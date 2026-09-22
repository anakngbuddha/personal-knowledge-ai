# PART2 Phase 4.2 - Advisor: gap analysis and recommendation

**Status: shipped.** Backend, chat tool, exports and 29 offline tests are on `main`.
No new dependencies. No new environment variables.

## What it does

The 4.1 customer brief plus the user's own product list, turned into the answer a
salesperson needs next: *"what else can I add from my product list?"*

Every recommendation returns the same six things, because that is what actually gets
used on a call:

1. a bundle grouped **by requirement**, with a reason per product;
2. clashes and prerequisites read off the **approved** product map;
3. requirements the product list cannot cover, stated as gaps;
4. upsell and cross-sell, drawn only from the product list;
5. questions still worth asking the customer;
6. assumptions a human must verify before it goes in a proposal.

## Files\n
| File | What it is |
|---|---|
| `backend/app/advisor/recommend.py` | The engine. A pure function over rows: `recommend_from_rows()`. |
| `backend/app/advisor/service.py` | The database half: product list, approved edges, evidence. |
| `backend/app/advisor/export.py` | Word and PowerPoint, both built from the same `Recommendation`. |
| `backend/app/api/routes/advisor.py` | `POST /advisor/recommend`, `POST /advisor/recommend/export`. |
| `backend/app/tools/advisor_tools.py` | `tool_advisor_recommend`, callable from chat. |
| `backend/tests/test_advisor_recommend.py` | 29 offline tests. No database, no API key. |

## Rules the code enforces (not just hopes for)

* **Nothing outside the product list is ever recommended.** The bundle is drawn from
  `products`. General knowledge may explain a choice; it may never invent a SKU.
* **Every pick is labelled.** Backed by one of the user's own documents (with the
  citation), or "general product knowledge" - and then repeated under *Verify before you
  send this*. The label survives into the Word file and the deck.
* **Only approved relationships count.** A pending suggestion on the map is not a
  compatibility guarantee, so it is never read as one.
* **A suggestion, a sample, or an end-of-life product is never quoted.**
* **No prices.** Ever. Always flagged as "quote from your current price list".

## Decisions worth knowing

* **A platform name alone is not a match.** Half a vendor's catalogue is "certified for
  Microsoft Teams", so matching only on the platform put a headset under "12 huddle
  rooms". A product now has to match something the customer asked for *besides* the
  platform, or be built for the room type. This was caught by the output, not by a test,
  and is now locked by `test_a_platform_name_alone_is_not_a_match`.
* **Evidence is fetched in two passes.** Pass one scores every product on text alone and
  costs nothing. Only the shortlist (10) gets a search, so a 2,000-product catalogue is
  not 2,000 queries per question.
* **A passage only counts as evidence for a product if it names it.** Hybrid search
  returns the *closest* passages, not passages about this product; attaching the nearest
  one anyway is how a citation ends up under a claim it does not support.
* **A clash drops the lower-scored side**, and says so in the gap list rather than
  silently shrinking the bundle.
* **Export is stateless.** The request carries the requirements, so there is no
  server-side draft to expire, leak, or clean up.
* **Two options per requirement.** More than that is a catalogue dump, not a
  recommendation. Tunable via `per_requirement`, not an env var.

## Endpoints

| Method | Path | Purpose |
|---|---|---|
| POST | `/advisor/recommend` | Bundle by requirement, clashes, gaps, upsell, questions, assumptions. `save_as_note` optional. |
| POST | `/advisor/recommend/export` | The same recommendation as `.docx` or `.pptx`. |

---

# PART2 Phase 4.3 - Notes UI: NOT STARTED

4.3 was **not** delivered in this pass. Nothing half-built was left on `main`: the 4.3
commits were not pushed, so the tree is consistent.

What 4.3 still needs, from PART2:

* a live markdown editor with `[[wikilinks]]` to products, accounts, notes and documents;
* a backlinks panel;
* a graph view combining notes, sources and products;
* "Save this answer as a note" from chat.

## Findings for whoever picks this up

These cost real time to establish, so they are recorded rather than rediscovered.

1. **Notes are already embedded on save.** `app/notes/index.py` chunks and embeds every
   note as a `Document` named `note:<uuid>.md`. So PART2 4.3's "embed and chunk notes on
   save" and 1.5 are already done. Two consequences: a note is retrievable by Ask
   immediately, and **any source picker or map must filter out `note:` documents** or it
   will offer a note to itself as a source.
2. **`[[document:...]]` cannot be stored as a `NoteLink` without a migration.**
   `NoteLinkKind` is `product | account | note`, and `note_links.target_kind` has a CHECK
   constraint mirroring it in `app/db/models.py`. Recommended route (simplest option that
   satisfies the acceptance tests, per PART2's own guidance): parse `[[source:...]]` /
   `[[document:...]]` at **read** time and resolve against live documents by
   `slugify(title or filename)`, without persisting a row. Notes and products have stable
   slugs and are worth indexing; uploaded files get superseded and re-titled, so a stored
   link to one is a stale row waiting to happen. This keeps the schema untouched.
3. **Backend surface to add:** `GET /notes/link-targets` (autocomplete),
   `GET /notes/graph` (nodes + edges), `GET /notes/{id}/backlinks`,
   `POST /notes/from-answer` (takes a `message_id` **or** raw `text` + citations; join
   `Message` to `Conversation` and filter on `Conversation.org_id` for tenant isolation).
   Route order matters: declare the literal paths **before** `GET /notes/{note_id}`.
4. **Frontend is a two-tree repo.** `frontend/src/` is the tree that is actually wired
   (`App.tsx` imports from it). `frontend/components/` - `BriefCard.tsx`,
   `Navigation.tsx`, `ThreePaneAsk.tsx`, and `backend/app/playbooks/brief*.py` - are an
   unwired parallel variant from an earlier pass. **Build in `frontend/src/`.**
5. **`frontend/src/index.css` is 47 KB.** Add new styles as a separate file imported from
   `main.tsx` rather than editing it.
6. **`request()` in `services/http.ts` times out at 15 seconds.** The advisor and any
   note-graph call over a large workspace need their own `fetch` with a longer budget,
   the way `askStream` already does.
7. **PART2 bans "ledger" and "tribal" in the UI.** The current Notes tab says "Tribal
   ledger". Renaming it is part of 4.3, not 5.1.
8. **Phase 5.1's navigation rewrite is also still outstanding** in `frontend/src/App.tsx`,
   which still shows the `01`-`08` numbered index. `CHANGELOG_phase45.md` claims Phase 5
   is done, but it describes the unwired `frontend/components/` tree. Treat that file's
   Phase 5 section as inaccurate.
