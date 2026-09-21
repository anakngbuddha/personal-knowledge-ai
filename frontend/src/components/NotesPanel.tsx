import { useEffect, useState } from "react";
import { api } from "../services/api";
import type { NoteRecord } from "../types";

export function NotesPanel() {
  const [notes, setNotes] = useState<NoteRecord[]>([]);
  const [total, setTotal] = useState(0);
  const [selected, setSelected] = useState<NoteRecord | null>(null);
  const [title, setTitle] = useState("");
  const [body, setBody] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  async function refresh() {
    try {
      const listed = await api.listNotes();
      setNotes(listed.notes);
      setTotal(listed.total);
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load notes");
    }
  }

  useEffect(() => {
    void refresh();
  }, []);

  function startNew() {
    setSelected(null);
    setTitle("");
    setBody("Link products with [[product:slug]] and accounts with [[account:acme-corp]].");
  }

  function open(note: NoteRecord) {
    setSelected(note);
    setTitle(note.title);
    setBody(note.body);
  }

  async function save() {
    setSaving(true);
    setError(null);
    try {
      const saved = selected
        ? await api.updateNote(selected.id, { title, body })
        : await api.createNote({ title, body });
      setSelected(saved);
      setTitle(saved.title);
      setBody(saved.body);
      await refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Save failed");
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="layout notes-desk">
      <section className="panel">
        <div className="panel-head">
          <div>
            <p className="kicker">07 · Field notes</p>
            <h2>Tribal ledger ({total})</h2>
          </div>
          <button type="button" className="primary" onClick={startNew}>
            New note
          </button>
        </div>
        {error && <div className="banner error">{error}</div>}
        {notes.length === 0 ? (
          <p className="empty-copy">
            No field notes yet. Capture sizing lore, caveats, and account-specific gotchas — then
            bind them with wikilinks so the catalog can find them later.
          </p>
        ) : (
          <ul className="note-index">
            {notes.map((note) => (
              <li key={note.id}>
                <button
                  type="button"
                  className={selected?.id === note.id ? "active" : ""}
                  onClick={() => open(note)}
                >
                  <span className="note-title">{note.title}</span>
                  <span className="muted">{note.slug}</span>
                </button>
              </li>
            ))}
          </ul>
        )}
      </section>
      <section className="panel">
        <div className="panel-head">
          <div>
            <p className="kicker">{selected ? selected.slug : "Draft"}</p>
            <h2>{selected ? "Revise" : "Compose"}</h2>
          </div>
          <button type="button" className="primary" disabled={saving || !title.trim()} onClick={() => void save()}>
            {saving ? "Stamping…" : "Save"}
          </button>
        </div>
        <label className="field-label" htmlFor="note-title">
          Title
        </label>
        <input
          id="note-title"
          className="chat-input"
          value={title}
          onChange={(e) => setTitle(e.target.value)}
          placeholder="Acme on-prem sizing"
        />
        <label className="field-label" htmlFor="note-body">
          Markdown
        </label>
        <textarea
          id="note-body"
          className="note-body"
          value={body}
          onChange={(e) => setBody(e.target.value)}
          rows={16}
          spellCheck={false}
        />
        {selected && (
          <div className="wikilink-row">
            {(selected.links || []).length === 0 ? (
              <span className="muted">No [[wikilinks]] extracted on last save.</span>
            ) : (
              selected.links.map((link) => (
                <span
                  key={`${link.target_kind}:${link.target_ref}`}
                  className={`stamp ${link.resolved ? "fresh" : "stale"}`}
                >
                  {link.target_kind}:{link.target_ref}
                  {link.resolved ? " · bound" : " · unresolved"}
                </span>
              ))
            )}
          </div>
        )}
      </section>
    </div>
  );
}
