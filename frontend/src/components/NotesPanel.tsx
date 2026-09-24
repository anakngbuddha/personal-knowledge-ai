import React, { useEffect, useRef, useState } from "react";
import { NotebookPicker } from "./NotebookPicker";
import { api } from "../services/api";
import type { LinkTargetOut, NoteGraphOut, NoteRecord } from "../types";
import "./NotesEditor.css";

type ViewMode = "editor" | "graph";

export function NotesPanel() {
  const [viewMode, setViewMode] = useState<ViewMode>("editor");
  const [notes, setNotes] = useState<NoteRecord[]>([]);
  const [total, setTotal] = useState(0);
  const [selected, setSelected] = useState<NoteRecord | null>(null);
  const [title, setTitle] = useState("");
  const [body, setBody] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [notebookId, setNotebookId] = useState<string | null>(null);

  // Wikilink autocomplete state
  const [suggestions, setSuggestions] = useState<LinkTargetOut[]>([]);
  const [showSuggestions, setShowSuggestions] = useState(false);
  const [cursorPos, setCursorPos] = useState<number>(0);
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  // Backlinks state
  const [backlinks, setBacklinks] = useState<NoteRecord[]>([]);
  const [loadingBacklinks, setLoadingBacklinks] = useState(false);

  // Graph view state
  const [graphData, setGraphData] = useState<NoteGraphOut | null>(null);
  const [loadingGraph, setLoadingGraph] = useState(false);

  async function refresh(nextNotebookId = notebookId) {
    try {
      const listed = await api.listNotes(50, 0, nextNotebookId ?? undefined);
      setNotes(listed.notes);
      setTotal(listed.total);
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load notes");
    }
  }

  useEffect(() => {
    void refresh(notebookId);
  }, [notebookId]);

  // Fetch backlinks when selected note changes
  useEffect(() => {
    if (!selected) {
      setBacklinks([]);
      return;
    }
    let active = true;
    setLoadingBacklinks(true);
    api
      .getBacklinks("note", selected.slug)
      .then((res) => {
        if (active) setBacklinks(res.notes);
      })
      .catch(() => {
        if (active) setBacklinks([]);
      })
      .finally(() => {
        if (active) setLoadingBacklinks(false);
      });
    return () => {
      active = false;
    };
  }, [selected?.id, selected?.slug]);

  // Fetch graph data when switching to graph view
  useEffect(() => {
    if (viewMode !== "graph") return;
    let active = true;
    setLoadingGraph(true);
    api
      .getNotesGraph()
      .then((res) => {
        if (active) setGraphData(res);
      })
      .catch((err) => {
        if (active) setError(err instanceof Error ? err.message : "Failed to load note graph");
      })
      .finally(() => {
        if (active) setLoadingGraph(false);
      });
    return () => {
      active = false;
    };
  }, [viewMode]);

  function startNew() {
    setSelected(null);
    setTitle("");
    setBody("Link products with [[product:slug]] or notes with [[note:slug]]. Type [[ to trigger autocomplete.");
    setShowSuggestions(false);
  }

  function open(note: NoteRecord) {
    setSelected(note);
    setTitle(note.title);
    setBody(note.body);
    setShowSuggestions(false);
  }

  async function save() {
    setSaving(true);
    setError(null);
    try {
      const saved = selected
        ? await api.updateNote(selected.id, { title, body })
        : await api.createNote({ title, body, notebook_id: notebookId ?? undefined });
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

  // Handle body textarea changes and [[ autocomplete trigger
  function handleBodyChange(e: React.ChangeEvent<HTMLTextAreaElement>) {
    const val = e.target.value;
    const pos = e.target.selectionStart;
    setBody(val);
    setCursorPos(pos);

    const left = val.slice(0, pos);
    const match = /\[\[([^\]]*)$/.exec(left);

    if (match) {
      const query = match[1];
      api
        .autocompleteWikilinks(query)
        .then((res) => {
          setSuggestions(res);
          setShowSuggestions(res.length > 0);
        })
        .catch(() => {
          setShowSuggestions(false);
        });
    } else {
      setShowSuggestions(false);
    }
  }

  function insertSuggestion(target: LinkTargetOut) {
    if (!textareaRef.current) return;
    const pos = cursorPos;
    const left = body.slice(0, pos);
    const right = body.slice(pos);
    const match = /\[\[([^\]]*)$/.exec(left);

    if (match) {
      const prefixIndex = match.index;
      const refString = target.kind ? `${target.kind}:${target.ref}` : target.ref;
      const newLeft = left.slice(0, prefixIndex) + `[[${refString}]]`;
      const newBody = newLeft + right;
      setBody(newBody);
      setShowSuggestions(false);

      setTimeout(() => {
        if (textareaRef.current) {
          textareaRef.current.focus();
          const newPos = newLeft.length;
          textareaRef.current.setSelectionRange(newPos, newPos);
        }
      }, 0);
    }
  }

  return (
    <div className="layout notes-desk">
      {/* Left Column: Notes List */}
      <section className="panel">
        <div className="panel-head">
          <div>
            <h2>Notes ({total})</h2>
          </div>
          <div style={{ display: "flex", gap: "8px" }}>
            <button
              type="button"
              className={viewMode === "editor" ? "primary" : "secondary"}
              onClick={() => setViewMode("editor")}
            >
              Editor
            </button>
            <button
              type="button"
              className={viewMode === "graph" ? "primary" : "secondary"}
              onClick={() => setViewMode("graph")}
            >
              Graph View
            </button>
          </div>
        </div>

        {viewMode === "editor" && (
          <>
            <div style={{ margin: "8px 0" }}>
              <button type="button" className="primary" onClick={startNew}>
                + New note
              </button>
            </div>
            <NotebookPicker notebookId={notebookId} onChange={setNotebookId} />
            {error && <div className="banner error">{error}</div>}
            {notes.length === 0 ? (
              <p className="empty-copy">
                No notes yet. Write what you learned about a customer or a product. Link a product with
                [[product:name]] or a note with [[note:title]].
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
          </>
        )}
      </section>

      {/* Right Column: Editor or Graph View */}
      <section className="panel" style={{ position: "relative" }}>
        {viewMode === "graph" ? (
          <div className="graph-view" style={{ height: "100%", display: "flex", flexDirection: "column" }}>
            <div className="panel-head">
              <div>
                <p className="kicker">Obsidian Knowledge Graph</p>
                <h2>Notes & Products Connections</h2>
              </div>
            </div>
            {loadingGraph ? (
              <div className="empty-copy">Loading knowledge graph…</div>
            ) : !graphData || graphData.nodes.length === 0 ? (
              <div className="empty-copy">No links between notes found yet. Create notes with [[wikilinks]].</div>
            ) : (
              <div className="notes-graph-canvas">
                <svg width="100%" height="100%" viewBox="0 0 600 400" style={{ width: "100%", height: "100%" }}>
                  {/* Render links */}
                  {graphData.edges.map((edge, idx) => {
                    const sourceNode = graphData.nodes.find((n) => n.id === edge.source_id);
                    const targetNode = graphData.nodes.find((n) => n.id === edge.target_id || n.slug === edge.target_ref);
                    const sIdx = graphData.nodes.indexOf(sourceNode!);
                    const tIdx = graphData.nodes.indexOf(targetNode!);

                    if (sIdx < 0 || tIdx < 0) return null;
                    const x1 = 100 + (sIdx % 4) * 140;
                    const y1 = 80 + Math.floor(sIdx / 4) * 100;
                    const x2 = 100 + (tIdx % 4) * 140;
                    const y2 = 80 + Math.floor(tIdx / 4) * 100;

                    return (
                      <line
                        key={`edge-${idx}`}
                        x1={x1}
                        y1={y1}
                        x2={x2}
                        y2={y2}
                        strokeWidth="2"
                        className={edge.resolved ? "edge resolved" : "edge"}
                      />
                    );
                  })}

                  {/* Render nodes */}
                  {graphData.nodes.map((node, i) => {
                    const cx = 100 + (i % 4) * 140;
                    const cy = 80 + Math.floor(i / 4) * 100;
                    const isNote = node.kind === "note";
                    return (
                      <g key={node.id} transform={`translate(${cx}, ${cy})`} style={{ cursor: "pointer" }}>
                        <circle
                          r="20"
                          className={isNote ? "node-dot node-note" : "node-dot node-product"}
                        />
                        <text textAnchor="middle" dy="4" fontSize="11" fontWeight="600">
                          {isNote ? "Note" : "Prod"}
                        </text>
                        <text textAnchor="middle" dy="34" fontSize="12">
                          {node.title.length > 14 ? `${node.title.slice(0, 12)}…` : node.title}
                        </text>
                      </g>
                    );
                  })}
                </svg>
              </div>
            )}
          </div>
        ) : (
          <>
            <div className="panel-head">
              <div>
                <p className="kicker">{selected ? selected.slug : "Draft"}</p>
                <h2>{selected ? "Revise" : "Compose"}</h2>
              </div>
              <button
                type="button"
                className="primary"
                disabled={saving || !title.trim()}
                onClick={() => void save()}
              >
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
              Markdown (type [[ to insert wikilinks)
            </label>

            <div style={{ position: "relative", flex: 1, display: "flex", flexDirection: "column" }}>
              <textarea
                id="note-body"
                ref={textareaRef}
                className="note-body"
                value={body}
                onChange={handleBodyChange}
                rows={14}
                spellCheck={false}
              />

              {/* Wikilink Autocomplete Dropdown */}
              {showSuggestions && (
                <div
                  className="link-suggestions"
                  style={{
                    position: "absolute",
                    bottom: "40px",
                    left: "12px",
                    right: "12px",
                    zIndex: 50,
                  }}
                >
                  {suggestions.map((item) => (
                    <div
                      key={`${item.kind}:${item.ref}`}
                      className="suggestion-item"
                      onClick={() => insertSuggestion(item)}
                    >
                      <span className="suggestion-kind">{item.kind}</span>
                      <span className="suggestion-title">{item.title}</span>
                      <span className="muted" style={{ fontSize: "11px" }}>
                        [[{item.ref}]]
                      </span>
                    </div>
                  ))}
                </div>
              )}
            </div>

            {/* Extracted Wikilinks Badges */}
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

            {/* Backlinks Side Panel / Section */}
            {selected && (
              <div className="backlinks-list">
                <h3>Backlinks ({backlinks.length})</h3>
                {loadingBacklinks ? (
                  <p className="muted" style={{ fontSize: "12px" }}>Loading backlinks…</p>
                ) : backlinks.length === 0 ? (
                  <p className="muted" style={{ fontSize: "12px" }}>No notes link to this note yet.</p>
                ) : (
                  <div style={{ display: "flex", flexWrap: "wrap", gap: "8px" }}>
                    {backlinks.map((bl) => (
                      <div
                        key={bl.id}
                        className="backlink-item"
                        onClick={() => open(bl)}
                        style={{ padding: "6px 12px", cursor: "pointer" }}
                      >
                        <div className="backlink-title">{bl.title}</div>
                        <div className="backlink-preview">slug: {bl.slug}</div>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            )}
          </>
        )}
      </section>
    </div>
  );
}
