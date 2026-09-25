# User Guide — Deep Atlas
 
Deep Atlas helps enterprise teams organize corporate documents, ask questions with verifiable citations, curate living notes, and explore neural knowledge maps.

**How to start**

1. Add documents under **Sources**.
2. Add your products under **Map** (or import a spreadsheet).
3. Open **Ask** and ask in plain language.

---

## Sign in

Open the app and sign in with your email and password, or create a workspace. Use **Settings** to sign out.

If the server has been idle, Ask may say it is waking up and will retry for about half a minute.

---

## Sources

Open **Sources**.

1. Click **Add source** and upload a PDF, Word, PowerPoint, Excel, or text file. Reading happens in the background. Vendor and product fields are optional extras.
2. When a file is ready, open it for the summary. Use **Suggested questions**, **Briefing**, or **FAQ**. **Find a passage** searches the text. **Watch a web page** notices when a public datasheet changes.
3. Scanned PDFs show **Read with OCR**. Sources that are not approved stay out of answers until you approve them.
4. Failed files show a plain reason and a **Retry** button.

---

## Notebooks

A notebook is one customer or deal. Create one on **Ask** or **Notes**.

- New notebooks switch on your real sources. Sample files stay off.
- Uncheck a source before you ask if it should not count for that deal.
- Notes, the customer brief, and chats started in a notebook stay with that notebook.

---

## Ask

Open **Ask**. Sources are on the left, the conversation is in the middle, and citations plus saved notes are on the right.

1. Pick a notebook and leave checked only the sources for this deal.
2. Ask in ordinary language. Choose **From my sources only** or **Sources + expert knowledge**.
3. Open a citation on the right. **Briefing**, **FAQ**, and **Compare** use the checked sources. **Save as note** keeps the answer.
4. **Suggested actions** under the composer start longer jobs (a spreadsheet of questions, a solution write-up, a support note, or an upgrade check). You still approve the draft before download.

Answers say what came from your documents, from general product knowledge, or from the web when a connection was used.

---

## Map

Open **Map** to add products, import a product list, review suggested links, and edit relationships without leaving the page.

---

## Suggested actions

These live under **Ask**.

| Action | What you provide | What you get |
|---|---|---|
| RFP responder | Customer spreadsheet | Cited answers, a review step, a Word file |
| Solution composer | Discovery notes | A checked bundle and a write-up |
| Incident triage | Logs plus what is installed | A cited runbook |
| Upgrade impact | Product and version | What would break, and alternatives |

---

## Connections

Open **Connections** to turn on web search, a browser for public pages, or Microsoft 365. Secrets stay on the server. Answers still work when these are off.

---

## Notes

Open **Notes**. Pick the notebook first. Write in Markdown. Links like `[[product:…]]`, `[[account:…]]`, and `[[note:…]]` become clickable. Saved notes can be found again when you Ask.

---

## Settings

**Settings** is where you sign out.

**Settings > Admin** (administrators only) shows:

- Workspace name and role
- **System status** (database, file storage, AI key, OCR, background jobs)
- Company sign-in and restore drills

Everyday screens do not show role or organization ids.

---

## Admin appendix

Deploy and local development details live in `README.md` and `.env.example`. Operators can also call `GET /health/dependencies` for the same checks shown under System status.

When you change the answer prompt version, re-run:

```bash
python scripts/run_generation_eval.py
```
