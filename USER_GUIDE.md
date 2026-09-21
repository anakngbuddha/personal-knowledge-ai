# User Guide — SE Field Desk

How to run and use the Solution Engineering Knowledge Workspace: grounded answers over your collateral, a typed product graph, HITL playbooks, MCP connectors, tribal notes, and vendor freshness watches.

The live stack is a Render API, Aiven PostgreSQL, and a Vercel frontend. Point the UI at the API with `VITE_API_BASE_URL` (no trailing slash). You can also open the frontend with `?api=https://personal-knowledge-ai-api.onrender.com`.

---

## 1. Sign in

Open the app and sign in with your email and password, or create a workspace. The server issues a signed session token. Production never uses the local-only `owner_dev` shortcut, and it will not start if `JWT_SECRET_KEY` is missing or too short.

Local tests may still set `AUTH_MODE=owner_dev`. Day-to-day development should use `AUTH_MODE=jwt` (see `.env.example`).

**SSO.** When `SSO_ENABLED=true`:

- OIDC: `GET /auth/oidc/start` returns an authorization URL. The IdP posts an ID token to `POST /auth/oidc/callback` (`{ "id_token", "nonce" }`). A valid token is exchanged for the same local session.
- SAML: `POST /auth/saml/acs` with `{ "SAMLResponse": "<Assertion>…</Assertion>", "signature": "<hmac hex>" }` (or `X-SAML-Signature`).

---

## 2. Sources

Open **Sources**.

1. Click **Add source** and upload a PDF, Word, PowerPoint, Excel, or text file. Files are read in the background. You do not need to fill vendor or product fields first — those are optional extras.
2. When a file is ready, ask questions about it. If a PDF was a scan, you will see **Read with OCR**. If a source is not approved, it is left out of answers until you approve it.
3. Status path: uploaded → processing → ready (or failed). Failed files show a plain-language reason and a Retry button.

---

## 3. Hybrid search

Open **05 Evidence**. Ask a question; the engine fuses pgvector similarity with Postgres full-text search (RRF). Hits show citation paths and a stale flag when `valid_until` has passed. Filter by vendor, product, or account when the corpus is large.

---

## 4. Grounded chat

Open **04 Desk**.

1. Ask as you would in an SE review. Answers cite chunks; unsupported claims are refused.
2. Turn **enable tools** on to let the model query the product graph and (if configured) MCP servers: Brave Search, Playwright snapshots of public docs, Microsoft 365 Graph.
3. Conversations persist per workspace. Click a citation to jump back to the source chunk.

Never treat chat output as approved collateral. Playbooks still pause at human gates.

---

## 5. Product graph

Open **03 Catalog**. Browse own and resold products, typed edges (`requires`, `conflicts_with`, `integrates_with`, …), and neighborhood / impact queries. Use this before composing a bundle so conflicts surface before the HLD.

---

## 6. Playbooks (workflows)

Open **01 Field runs**.

| Playbook | What you provide | What you get |
|---|---|---|
| RFP responder | Customer spreadsheet | Cited answers, HITL review, DOCX |
| Solution composer | Discovery notes | Conflict-checked bundle, HLD, BOM |
| Incident triage | Logs + install base | Cited runbook |
| Upgrade impact | Product / version | Transitive breaks and alternatives |

1. Start a run from the gallery.
2. Watch the task tree (`pending` → `running` → `waiting_approval` / `succeeded`).
3. On a gate, compare the draft, citations, and graph warnings; edit; **Approve & resume** or reject.
4. Download the deliverable when the run succeeds.

Runs live in Postgres. They survive deploys and overnight pauses.

---

## 7. MCP connectors

Open **02 Connectors** (admin). Enable Playwright, Microsoft 365, or Brave Search per org. Secrets are encrypted at rest and never returned. Use **Test** to list tools. Catalog tools stay available even when MCP is off.

---

## 8. Field notes (`[[wikilinks]]`)

Open **07 Ledger**.

Write Markdown. On save, `[[product:firewall-plus]]`, `[[account:acme-corp]]`, and `[[note:sizing-acme]]` become typed links. Unprefixed `[[firewall-plus]]` resolves against products, then notes. Bound links show **bound**; missing targets stay **unresolved**.

Notes are tenant-scoped. They are the SE tribal record — caveats, sizing lore, account-specific gotchas — not a substitute for approved datasheets.

---

## 9. Freshness watches and restore drills

Open **08 Watch**.

1. Register a public vendor URL (datasheet, compatibility matrix). The poller fetches it through the SSRF-safe client and stores a SHA-256 digest.
2. A digest change raises a **staleness alert**. Acknowledge it after you ingest the new file.
3. Admins run **Restore drill**: logical dump of notes/watches → scratch restore → row-count compare, timed against `RESTORE_DRILL_SLA_SECONDS` (default 300s). CLI: `python scripts/restore_drill.py`.

---

## 10. Local run

```bash
# Backend
cd backend
python -m venv .venv && .venv/Scripts/activate   # Windows
pip install -r requirements.txt
# DATABASE_URL must be postgresql+psycopg://… ; Aiven URIs need ?sslmode=require
python ../scripts/init_db.py
uvicorn app.main:app --reload
```

```bash
# Frontend
cd frontend
npm install
# .env: VITE_API_BASE_URL=http://localhost:8000
npm run dev
```

Open http://localhost:5173. Without keys, `STORAGE_BACKEND=local`, `EMBEDDING_PROVIDER=fake`, and `LLM_PROVIDER=fake` still exercise the full loop.

---

## Roles (short)

| Role | Typical work |
|---|---|
| `viewer` | Read approved collateral |
| `sales` | Search and chat within grants |
| `solutions_engineer` | Notes, watches, playbooks, catalog writes |
| `admin` / `owner` | SSO, MCP secrets, restore drills, all accounts |

Cross-tenant IDs 404. Do not share database credentials in tickets or chat; rotate anything that has been pasted into a transcript.
