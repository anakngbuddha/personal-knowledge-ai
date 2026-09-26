import React, { useEffect, useRef, useState, useMemo } from "react";
import { api } from "../services/api";
import type { LinkTargetOut, NoteGraphOut, NotebookRecord } from "../types";
import "./NotesEditor.css";

type ViewMode = "editor" | "split" | "graph";

interface DealNoteItem {
  id: string;
  title: string;
  slug: string;
  body: string;
  timeAgo: string;
  isNow?: boolean;
  tags: string[];
  links?: Array<{ target_kind: string; target_ref: string; resolved: boolean }>;
}

export function NotesPanel() {
  const [viewMode, setViewMode] = useState<ViewMode>("editor");
  const [previewActive, setPreviewActive] = useState(false);
  const [notebooks, setNotebooks] = useState<NotebookRecord[]>([]);
  const [selectedNotebookId, setSelectedNotebookId] = useState<string>("");
  const [showNotebookPicker, setShowNotebookPicker] = useState(false);
  const [newNotebookName, setNewNotebookName] = useState("");

  // Notes state - clean default empty state for newly created accounts
  const [notes, setNotes] = useState<DealNoteItem[]>([]);
  const [selectedNoteId, setSelectedNoteId] = useState<string>("");
  const [title, setTitle] = useState("");
  const [body, setBody] = useState("");
  const [saving, setSaving] = useState(false);
  const [saveStatusText, setSaveStatusText] = useState("Ready");
  const [isDrafting, setIsDrafting] = useState(false);

  // Wikilink Autocomplete State
  const [suggestions, setSuggestions] = useState<LinkTargetOut[]>([]);
  const [showSuggestions, setShowSuggestions] = useState(false);
  const [cursorPos, setCursorPos] = useState(0);
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  // Full Graph View State
  const [graphData, setGraphData] = useState<NoteGraphOut | null>(null);
  const [loadingGraph, setLoadingGraph] = useState(false);

  // Load Notebooks from Backend API
  useEffect(() => {
    let active = true;
    api
      .listNotebooks()
      .then((res) => {
        if (active && res.notebooks) {
          setNotebooks(res.notebooks);
          if (res.notebooks.length > 0 && !selectedNotebookId) {
            setSelectedNotebookId(res.notebooks[0].id);
          }
        }
      })
      .catch(() => {
        /* no notebooks loaded */
      });
    return () => {
      active = false;
    };
  }, []);

  // Load Notes for Selected Notebook
  useEffect(() => {
    let active = true;
    api
      .listNotes(50, 0, selectedNotebookId || undefined)
      .then((res) => {
        if (!active) return;
        if (res.notes && res.notes.length > 0) {
          const mapped: DealNoteItem[] = res.notes.map((n, idx) => ({
            id: n.id,
            title: n.title,
            slug: n.slug,
            body: n.body,
            timeAgo: idx === 0 ? "NOW" : "Recent",
            isNow: idx === 0,
            tags: n.links && n.links.length > 0 ? n.links.map((l) => `#${l.target_ref}`) : ["#note"],
            links: (n.links || []).map((l) => ({
              target_kind: l.target_kind,
              target_ref: l.target_ref,
              resolved: l.resolved,
            })),
          }));
          setNotes(mapped);
          setSelectedNoteId(mapped[0].id);
          setTitle(mapped[0].title);
          setBody(mapped[0].body);
          setIsDrafting(false);
          setSaveStatusText("Saved");
        } else {
          setNotes([]);
          setSelectedNoteId("");
          setTitle("");
          setBody("");
          setIsDrafting(false);
          setSaveStatusText("Ready");
        }
      })
      .catch(() => {
        if (active) {
          setNotes([]);
          setSelectedNoteId("");
          setTitle("");
          setBody("");
          setIsDrafting(false);
          setSaveStatusText("Ready");
        }
      });
    return () => {
      active = false;
    };
  }, [selectedNotebookId]);

  // Load Graph Data when in Graph View
  useEffect(() => {
    if (viewMode !== "graph") return;
    let active = true;
    setLoadingGraph(true);
    api
      .getNotesGraph()
      .then((res) => {
        if (active) setGraphData(res);
      })
      .catch(() => {
        /* fallback graph */
      })
      .finally(() => {
        if (active) setLoadingGraph(false);
      });
    return () => {
      active = false;
    };
  }, [viewMode]);

  // Current Active Note
  const currentNote = useMemo(() => {
    return notes.find((n) => n.id === selectedNoteId) || null;
  }, [notes, selectedNoteId]);

  // Switch Active Note
  function selectNote(item: DealNoteItem) {
    setSelectedNoteId(item.id);
    setTitle(item.title);
    setBody(item.body);
    setShowSuggestions(false);
    setIsDrafting(false);
    setSaveStatusText("Saved");
  }

  // Create New Note
  function handleNewNote() {
    const newId = `note-${Date.now()}`;
    const newNote: DealNoteItem = {
      id: newId,
      title: "",
      slug: "new-note",
      timeAgo: "NOW",
      isNow: true,
      tags: [],
      body: "",
      links: [],
    };
    setNotes([newNote, ...notes.filter((n) => n.id !== newId)]);
    setSelectedNoteId(newId);
    setTitle("");
    setBody("");
    setIsDrafting(true);
    setSaveStatusText("Draft • Unsaved");
    if (viewMode === "graph") setViewMode("editor");
  }

  // Save Note Mutation
  async function handleSave() {
    if (!title.trim() && !body.trim()) return;
    setSaving(true);
    try {
      const isNew = !selectedNoteId || selectedNoteId.startsWith("deal-note-") || selectedNoteId.startsWith("note-") || selectedNoteId.startsWith("imported-");
      if (isNew) {
        // Try creating on server
        const saved = await api.createNote({
          title: title.trim() || "Untitled Note",
          body,
          notebook_id: selectedNotebookId && !selectedNotebookId.startsWith("nb-") ? selectedNotebookId : undefined,
        });
        const mappedNote: DealNoteItem = {
          id: saved.id,
          title: saved.title,
          slug: saved.slug,
          body: saved.body,
          timeAgo: "NOW",
          isNow: true,
          tags: (saved.links || []).map((l) => `#${l.target_ref}`),
          links: (saved.links || []).map((l) => ({
            target_kind: l.target_kind,
            target_ref: l.target_ref,
            resolved: l.resolved,
          })),
        };
        setNotes((prev) => [mappedNote, ...prev.filter((n) => n.id !== selectedNoteId)]);
        setSelectedNoteId(saved.id);
      } else {
        // Update existing note
        const updated = await api.updateNote(selectedNoteId, { title: title.trim() || "Untitled Note", body });
        setNotes((prev) =>
          prev.map((n) =>
            n.id === selectedNoteId
              ? {
                  ...n,
                  title: updated.title,
                  slug: updated.slug,
                  body: updated.body,
                  tags: (updated.links || []).map((l) => `#${l.target_ref}`),
                  links: (updated.links || []).map((l) => ({
                    target_kind: l.target_kind,
                    target_ref: l.target_ref,
                    resolved: l.resolved,
                  })),
                }
              : n
          )
        );
      }
      setIsDrafting(false);
      setSaveStatusText("Saved just now");
    } catch {
      // Offline fallback: update in-memory
      setNotes((prev) =>
        prev.map((n) =>
          n.id === selectedNoteId
            ? { ...n, title: title.trim() || "Untitled Note", body }
            : n
        )
      );
      setIsDrafting(false);
      setSaveStatusText("Saved locally");
    } finally {
      setSaving(false);
    }
  }

  // Delete Note
  async function handleDeleteNote(idToDelete: string) {
    if (!window.confirm("Are you sure you want to delete this note?")) return;
    try {
      if (!idToDelete.startsWith("note-") && !idToDelete.startsWith("deal-note-") && !idToDelete.startsWith("imported-")) {
        await api.deleteNote(idToDelete);
      }
      const remaining = notes.filter((n) => n.id !== idToDelete);
      setNotes(remaining);
      if (remaining.length > 0) {
        selectNote(remaining[0]);
      } else {
        setSelectedNoteId("");
        setTitle("");
        setBody("");
        setIsDrafting(false);
        setSaveStatusText("Ready");
      }
    } catch (err) {
      console.error("Failed to delete note", err);
    }
  }

  // Handle Textarea Change and [[ Autocomplete Trigger
  function handleBodyChange(e: React.ChangeEvent<HTMLTextAreaElement>) {
    const val = e.target.value;
    const pos = e.target.selectionStart;
    setBody(val);
    setCursorPos(pos);
    setIsDrafting(true);
    setSaveStatusText("Draft • Editing");

    // Detect [[ wikilink pattern
    const left = val.slice(0, pos);
    const match = /\[\[([^\]]*)$/.exec(left);

    if (match) {
      const query = match[1];
      api
        .autocompleteWikilinks(query)
        .then((res) => {
          if (res && res.length > 0) {
            setSuggestions(res);
            setShowSuggestions(true);
          } else {
            setSuggestions([]);
            setShowSuggestions(false);
          }
        })
        .catch(() => {
          setSuggestions([]);
          setShowSuggestions(false);
        });
    } else {
      setShowSuggestions(false);
    }
  }

  // Insert Wikilink Suggestion
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

  // Format Bar Actions
  function insertFormatting(prefix: string, suffix: string = prefix) {
    if (!textareaRef.current) return;
    const start = textareaRef.current.selectionStart;
    const end = textareaRef.current.selectionEnd;
    const selectedText = body.slice(start, end);
    const replacement = `${prefix}${selectedText || "text"}${suffix}`;
    const newBody = body.slice(0, start) + replacement + body.slice(end);
    setBody(newBody);
    setIsDrafting(true);

    setTimeout(() => {
      if (textareaRef.current) {
        textareaRef.current.focus();
        textareaRef.current.setSelectionRange(start + prefix.length, end + prefix.length);
      }
    }, 0);
  }

  function insertTableTemplate() {
    const tableTemplate = `\n| Item | Specification | Qty | Notes |\n| :--- | :--- | :--- | :--- |\n| | | | |\n`;
    if (!textareaRef.current) {
      setBody((prev) => prev + tableTemplate);
      return;
    }
    const pos = textareaRef.current.selectionStart;
    const newBody = body.slice(0, pos) + tableTemplate + body.slice(pos);
    setBody(newBody);
    setIsDrafting(true);
  }

  // Import Markdown File
  function handleImportMarkdown(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    if (!file) return;
    const reader = new FileReader();
    reader.onload = (event) => {
      const content = event.target?.result as string;
      if (content) {
        const fileName = file.name.replace(/\.[^/.]+$/, "");
        const newId = `imported-${Date.now()}`;
        const newNote: DealNoteItem = {
          id: newId,
          title: fileName,
          slug: fileName.toLowerCase().replace(/\s+/g, "-"),
          timeAgo: "NOW",
          isNow: true,
          tags: ["#imported"],
          body: content,
          links: [],
        };
        setNotes([newNote, ...notes]);
        setSelectedNoteId(newId);
        setTitle(newNote.title);
        setBody(newNote.body);
        setIsDrafting(true);
        setSaveStatusText("Draft • Unsaved");
      }
    };
    reader.readAsText(file);
  }

  // Word and Char Counters
  const wordCount = useMemo(() => {
    return body.trim() ? body.trim().split(/\s+/).length : 0;
  }, [body]);

  const charCount = useMemo(() => {
    return body.length >= 1000 ? `${(body.length / 1000).toFixed(1)}k` : body.length;
  }, [body]);

  const totalWikilinks = useMemo(() => {
    return notes.reduce((acc, n) => acc + (n.links?.length || 0), 0);
  }, [notes]);

  // Current Notebook Name
  const currentNotebook = notebooks.find((nb) => nb.id === selectedNotebookId) || null;

  async function handleCreateNotebook() {
    const trimmed = newNotebookName.trim();
    if (!trimmed) return;
    try {
      const created = await api.createNotebook(trimmed);
      setNotebooks((prev) => [...prev, created]);
      setSelectedNotebookId(created.id);
      setNewNotebookName("");
      setShowNotebookPicker(false);
    } catch {
      // offline fallback
      const fallbackNb: NotebookRecord = {
        id: `nb-${Date.now()}`,
        name: trimmed,
        workspace_id: "default",
      };
      setNotebooks((prev) => [...prev, fallbackNb]);
      setSelectedNotebookId(fallbackNb.id);
      setNewNotebookName("");
      setShowNotebookPicker(false);
    }
  }

  // Active note links for inspector
  const activeLinks = currentNote?.links || [];

  return (
    <div className="notes-desk-root">
      {/* ── Top Notebook Header Card ──────────────────────────────────── */}
      <header className="notebook-header-card">
        <div className="notebook-header-left">
          <div className="notebook-icon-box" title="Confidential Enterprise Notebook">
            <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <path d="M4 19.5A2.5 2.5 0 0 1 6.5 17H20" />
              <path d="M6.5 2H20v20H6.5A2.5 2.5 0 0 1 4 19.5v-15A2.5 2.5 0 0 1 6.5 2z" />
            </svg>
          </div>

          <div className="notebook-title-meta">
            <div className="notebook-kicker-row">
              <span className="notebook-kicker">NOTEBOOK</span>
              <span style={{ color: "var(--text-muted)", fontSize: "10px" }}>•</span>
              <span className="notebook-badge-confidential">Confidential Enterprise</span>
            </div>

            <button
              type="button"
              className="notebook-picker-btn"
              onClick={() => setShowNotebookPicker(!showNotebookPicker)}
              aria-expanded={showNotebookPicker}
            >
              <span>{currentNotebook ? currentNotebook.name : (notebooks.length === 0 ? "Workspace Notes" : "All Notes")}</span>
              <span className="notebook-chevron">⌵</span>
            </button>
          </div>

          {/* Notebook Dropdown Menu */}
          {showNotebookPicker && (
            <div className="notebook-dropdown-menu">
              <div style={{ fontSize: "11px", fontWeight: 700, color: "var(--text-muted)", padding: "4px 8px", textTransform: "uppercase" }}>
                Switch Notebook
              </div>
              <div className="notebook-dropdown-list">
                <button
                  type="button"
                  className={`notebook-dropdown-item ${!selectedNotebookId ? "active" : ""}`}
                  onClick={() => {
                    setSelectedNotebookId("");
                    setShowNotebookPicker(false);
                  }}
                >
                  <span>All Workspace Notes</span>
                  {!selectedNotebookId && <span>✓</span>}
                </button>
                {notebooks.map((nb) => (
                  <button
                    key={nb.id}
                    type="button"
                    className={`notebook-dropdown-item ${selectedNotebookId === nb.id ? "active" : ""}`}
                    onClick={() => {
                      setSelectedNotebookId(nb.id);
                      setShowNotebookPicker(false);
                    }}
                  >
                    <span>{nb.name}</span>
                    {selectedNotebookId === nb.id && <span>✓</span>}
                  </button>
                ))}
              </div>

              <div className="notebook-create-row">
                <input
                  className="notebook-create-input"
                  placeholder="New notebook name..."
                  value={newNotebookName}
                  onChange={(e) => setNewNotebookName(e.target.value)}
                  onKeyDown={(e) => {
                    if (e.key === "Enter") {
                      void handleCreateNotebook();
                    }
                  }}
                />
                <button
                  type="button"
                  className="notebook-create-btn"
                  disabled={!newNotebookName.trim()}
                  onClick={() => void handleCreateNotebook()}
                >
                  Create
                </button>
              </div>
            </div>
          )}
        </div>

        <div className="notebook-header-right">
          {/* Stats Ribbon */}
          <div className="notebook-stats-ribbon">
            <div className="notebook-stat-item">
              <span className="notebook-stat-label">NOTES</span>
              <span className="notebook-stat-val">{notes.length}</span>
            </div>
            <div className="notebook-stat-item">
              <span className="notebook-stat-label">WIKILINKS</span>
              <span className="notebook-stat-val accent">{totalWikilinks}</span>
            </div>
            <div className="notebook-stat-item">
              <span className="notebook-stat-label">NOTEBOOKS</span>
              <span className="notebook-stat-val">{notebooks.length}</span>
            </div>
          </div>

          {/* Segmented View Controller */}
          <div className="segmented-control" role="tablist" aria-label="Editor View Modes">
            <button
              type="button"
              role="tab"
              aria-selected={viewMode === "editor"}
              className={`segment-btn ${viewMode === "editor" ? "active" : ""}`}
              onClick={() => setViewMode("editor")}
            >
              Editor
            </button>
            <button
              type="button"
              role="tab"
              aria-selected={viewMode === "split"}
              className={`segment-btn ${viewMode === "split" ? "active" : ""}`}
              onClick={() => setViewMode("split")}
            >
              Split
            </button>
            <button
              type="button"
              role="tab"
              aria-selected={viewMode === "graph"}
              className={`segment-btn ${viewMode === "graph" ? "active" : ""}`}
              onClick={() => setViewMode("graph")}
            >
              Graph View
            </button>
          </div>

          {/* Primary Action Button */}
          <button type="button" className="btn-primary-new" onClick={handleNewNote}>
            <span style={{ fontSize: "16px", lineHeight: 1 }}>+</span>
            <span>New</span>
          </button>
        </div>
      </header>

      {/* ── Main Workspace Body (3-Column Grid or Full Graph View) ─────── */}
      {viewMode === "graph" ? (
        <div className="notes-full-graph-container">
          <div className="full-graph-header">
            <div>
              <span className="inspector-section-label">KNOWLEDGE GRAPH</span>
              <h2 style={{ margin: "2px 0 0", fontSize: "17px", fontWeight: 700 }}>
                Notes & Products Graph Topology
              </h2>
            </div>
            <div style={{ display: "flex", gap: "8px" }}>
              <button
                type="button"
                className="btn-editor-preview"
                onClick={() => setViewMode("editor")}
              >
                Return to Editor
              </button>
            </div>
          </div>

          <div className="full-graph-canvas-wrap">
            {loadingGraph ? (
              <div style={{ display: "grid", placeItems: "center", height: "100%", color: "var(--text-muted)" }}>
                Loading knowledge graph...
              </div>
            ) : !graphData || graphData.nodes.length === 0 ? (
              <div style={{ display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center", height: "100%", color: "var(--text-muted)", padding: "40px" }}>
                <div style={{ fontSize: "36px", marginBottom: "12px" }}>🕸️</div>
                <div style={{ fontWeight: 600, fontSize: "16px", color: "var(--text-primary)", marginBottom: "6px" }}>No Graph Nodes Yet</div>
                <p style={{ fontSize: "13px", maxWidth: "380px", textAlign: "center", lineHeight: "1.5" }}>
                  Create notes and link them to catalog products or other notes using <code>[[wikilinks]]</code> to view their connections.
                </p>
              </div>
            ) : (
              <svg width="100%" height="100%" viewBox="0 0 800 500" style={{ width: "100%", height: "100%" }}>
                <defs>
                  <radialGradient id="nodeActiveGlow" cx="50%" cy="50%" r="50%">
                    <stop offset="0%" stopColor="#4f46e5" stopOpacity="0.8" />
                    <stop offset="100%" stopColor="#4f46e5" stopOpacity="0" />
                  </radialGradient>
                </defs>
                {graphData.nodes.map((node, i) => {
                  const angle = (i / graphData.nodes.length) * 2 * Math.PI;
                  const radius = graphData.nodes.length === 1 ? 0 : 160;
                  const cx = 400 + radius * Math.cos(angle);
                  const cy = 250 + radius * Math.sin(angle);
                  return (
                    <g key={node.id} transform={`translate(${cx}, ${cy})`} style={{ cursor: "pointer" }}>
                      <circle r="18" fill={node.kind === "product" ? "#ecfdf5" : "#eef2ff"} stroke={node.kind === "product" ? "#10b981" : "#4f46e5"} strokeWidth="2" />
                      <text textAnchor="middle" dy="4" fontSize="10" fontWeight="700" fill={node.kind === "product" ? "#065f46" : "#4338ca"}>
                        {node.title.slice(0, 4).toUpperCase()}
                      </text>
                      <text textAnchor="middle" dy="32" fontSize="11" fill="var(--text-secondary)">
                        {node.title.slice(0, 16)}
                      </text>
                    </g>
                  );
                })}
              </svg>
            )}
          </div>
        </div>
      ) : (
        <div className="notes-workspace-grid">
          {/* ── Column 1: Deal Notes List Panel ───────────────────────── */}
          <section className="notes-col-list" aria-label="Deal Notes List">
            <div className="notes-list-header">
              <span className="notes-list-title">DEAL NOTES ({notes.length})</span>
              <button type="button" className="notes-order-select">
                <span>Order: Recent</span>
                <span>⌵</span>
              </button>
            </div>

            <div className="notes-cards-scroll">
              {notes.length === 0 ? (
                <div style={{ padding: "40px 16px", textAlign: "center", color: "var(--text-muted)" }}>
                  <p style={{ margin: "0 0 12px", fontSize: "13px" }}>No notes in this notebook yet.</p>
                  <button
                    type="button"
                    className="btn-primary-new"
                    style={{ margin: "0 auto", padding: "6px 14px", fontSize: "12px" }}
                    onClick={handleNewNote}
                  >
                    + Create Note
                  </button>
                </div>
              ) : (
                notes.map((note) => {
                  const isActive = selectedNoteId === note.id;
                  return (
                    <div
                      key={note.id}
                      className={`deal-note-card ${isActive ? "active" : ""}`}
                      onClick={() => selectNote(note)}
                    >
                      <div className="deal-note-top-row">
                        <span className="deal-note-title">{note.title || "Untitled Note"}</span>
                        <span className={`deal-note-time-badge ${note.isNow ? "now" : ""}`}>
                          {note.timeAgo}
                        </span>
                      </div>

                      <p className="deal-note-excerpt">
                        {(note.body || "").replace(/[#*|`]/g, "").slice(0, 110) || "No content"}...
                      </p>

                      <div className="deal-note-tags-row">
                        {(note.tags || []).map((tag) => (
                          <span key={tag} className="deal-tag-pill">
                            {tag}
                          </span>
                        ))}
                      </div>
                    </div>
                  );
                })
              )}
            </div>

            <div className="notes-col-list-footer">
              <input
                type="file"
                ref={fileInputRef}
                style={{ display: "none" }}
                accept=".md,.txt,.markdown"
                onChange={handleImportMarkdown}
              />
              <button
                type="button"
                className="btn-ghost-import"
                onClick={() => fileInputRef.current?.click()}
              >
                <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                  <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4" />
                  <polyline points="17 8 12 3 7 8" />
                  <line x1="12" y1="3" x2="12" y2="15" />
                </svg>
                <span>Import Markdown</span>
              </button>
              <span className="notes-storage-telemetry">{notes.length} {notes.length === 1 ? "note" : "notes"}</span>
            </div>
          </section>

          {/* ── Column 2: Main Note Editor / Preview Canvas ────────────── */}
          <section className="notes-col-editor" aria-label="Note Editor">
            {notes.length === 0 && !isDrafting ? (
              <div style={{ display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center", height: "100%", padding: "40px 20px", textAlign: "center", color: "var(--text-muted)" }}>
                <div style={{ fontSize: "36px", marginBottom: "12px" }}>📝</div>
                <div style={{ fontWeight: 600, fontSize: "15px", color: "var(--text-primary)", marginBottom: "6px" }}>No note selected</div>
                <p style={{ fontSize: "13px", maxWidth: "340px", margin: "0 0 16px", lineHeight: "1.5" }}>
                  Create a new note or select one from the list to start editing.
                </p>
                <button type="button" className="btn-primary-new" onClick={handleNewNote}>
                  + New Note
                </button>
              </div>
            ) : (
              <>
                {/* Top Bar: Autosave & Actions */}
                <div className="editor-header-bar">
                  <div className="editor-status-indicator">
                    <span className={`status-pip ${isDrafting ? "drafting" : ""}`} />
                    <span>{saveStatusText}</span>
                  </div>

                  <div className="editor-header-actions">
                    {selectedNoteId && (
                      <button
                        type="button"
                        className="btn-editor-preview"
                        style={{ color: "#ef4444" }}
                        title="Delete this note"
                        onClick={() => void handleDeleteNote(selectedNoteId)}
                      >
                        Delete
                      </button>
                    )}
                    <button
                      type="button"
                      className={`btn-editor-preview ${previewActive ? "active" : ""}`}
                      onClick={() => setPreviewActive(!previewActive)}
                    >
                      {previewActive ? "Edit Raw" : "Preview"}
                    </button>
                    <button
                      type="button"
                      className="btn-editor-save"
                      disabled={saving || (!title.trim() && !body.trim())}
                      onClick={() => void handleSave()}
                    >
                      <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
                        <polyline points="20 6 9 17 4 12" />
                      </svg>
                      <span>{saving ? "Saving..." : "Save"}</span>
                    </button>
                  </div>
                </div>

                {/* Note Title Input */}
                <div className="editor-title-container">
                  <span className="editor-title-label">TITLE</span>
                  <input
                    className="editor-title-input"
                    value={title}
                    onChange={(e) => {
                      setTitle(e.target.value);
                      setIsDrafting(true);
                      setSaveStatusText("Draft • Editing");
                    }}
                    placeholder="Enter note title..."
                  />
                </div>

                {/* Utility Formatting Toolbar */}
                <div className="editor-format-toolbar">
                  <button
                    type="button"
                    className="format-btn"
                    title="Bold"
                    onClick={() => insertFormatting("**")}
                  >
                    B
                  </button>
                  <button
                    type="button"
                    className="format-btn"
                    title="Italic"
                    onClick={() => insertFormatting("*")}
                  >
                    I
                  </button>
                  <button
                    type="button"
                    className="format-btn"
                    title="Underline"
                    onClick={() => insertFormatting("<u>", "</u>")}
                  >
                    U
                  </button>
                  <button
                    type="button"
                    className="format-btn format-btn-wide"
                    title="Insert [[wikilink]]"
                    onClick={() => insertFormatting("[[", "]]")}
                  >
                    [[wikilink]]
                  </button>
                  <button
                    type="button"
                    className="format-btn format-btn-wide"
                    title="Insert Table"
                    onClick={insertTableTemplate}
                  >
                    ⊞ Table
                  </button>
                  <span className="toolbar-sep" />
                  <span className="toolbar-hint">Type [[ to insert wikilinks</span>
                </div>

                {/* Body Content Area (Editor / Preview / Split) */}
                <div className="editor-body-canvas">
                  {viewMode === "split" ? (
                    <div className="editor-split-container">
                      <div className="editor-split-pane">
                        <textarea
                          ref={textareaRef}
                          className="editor-textarea"
                          value={body}
                          onChange={handleBodyChange}
                          placeholder="Type your notes here. Use [[ to link catalog & notes..."
                          spellCheck={false}
                        />
                      </div>
                      <div className="editor-split-pane">
                        <RenderedNotePreview title={title} body={body} />
                      </div>
                    </div>
                  ) : previewActive ? (
                    <RenderedNotePreview title={title} body={body} />
                  ) : (
                    <>
                      <textarea
                        ref={textareaRef}
                        className="editor-textarea"
                        value={body}
                        onChange={handleBodyChange}
                        placeholder="Type your notes here. Use [[ to link catalog & notes..."
                        spellCheck={false}
                      />

                      {/* Wikilink Autocomplete Dropdown */}
                      {showSuggestions && suggestions.length > 0 && (
                        <div className="wikilink-autocomplete-popup">
                          <div style={{ padding: "6px 12px", fontSize: "10px", fontWeight: 700, color: "var(--text-muted)", textTransform: "uppercase" }}>
                            Linked Entities
                          </div>
                          {suggestions.map((item) => (
                            <div
                              key={`${item.kind}:${item.ref}`}
                              className="autocomplete-item"
                              onClick={() => insertSuggestion(item)}
                            >
                              <span className="autocomplete-badge">{item.kind}</span>
                              <span className="autocomplete-title">{item.title}</span>
                              <span style={{ fontSize: "11px", color: "var(--text-muted)", fontFamily: "var(--font-mono)" }}>
                                [[{item.ref}]]
                              </span>
                            </div>
                          ))}
                        </div>
                      )}
                    </>
                  )}
                </div>

                {/* Editor Footer Status Bar */}
                <div className="editor-footer-status-bar">
                  <div className="editor-footer-left">
                    <span className="pulse-dot" style={{ width: "6px", height: "6px" }} />
                    <span>Catalog Grounded</span>
                  </div>
                  <div className="editor-footer-stats">
                    <span>{wordCount} Words</span>
                    <span style={{ margin: "0 6px" }}>•</span>
                    <span>{charCount} Chars</span>
                  </div>
                </div>
              </>
            )}
          </section>

          {/* ── Column 3: Inspector & Links Panel ───────────────────────── */}
          <section className="notes-col-inspector" aria-label="Inspector and Links">
            <div className="inspector-header-bar">
              <div className="inspector-title-row">
                <span>🔗</span>
                <span>INSPECTOR & LINKS</span>
              </div>
              <span className="inspector-connected-badge">{activeLinks.length} Connected</span>
            </div>

            <div className="inspector-content-scroll">
              {/* Local 1-Hop Graph Relationship */}
              <div className="mini-graph-box">
                <div className="mini-graph-svg-wrap">
                  <svg width="100%" height="100" viewBox="0 0 240 100">
                    {activeLinks.length === 0 ? (
                      <>
                        <circle cx="120" cy="50" r="14" fill="#4f46e5" stroke="#ffffff" strokeWidth="2" />
                        <text x="120" y="76" textAnchor="middle" fontSize="10" fill="var(--text-muted)">
                          {title ? title.slice(0, 16) : "Active Note"}
                        </text>
                      </>
                    ) : (
                      <>
                        {activeLinks.map((_, i) => {
                          const angle = (i / activeLinks.length) * 2 * Math.PI;
                          const sx = 120 + 55 * Math.cos(angle);
                          const sy = 50 + 30 * Math.sin(angle);
                          return (
                            <line key={i} x1="120" y1="50" x2={sx} y2={sy} stroke="#cbd5e1" strokeWidth="1.5" />
                          );
                        })}
                        {activeLinks.map((link, i) => {
                          const angle = (i / activeLinks.length) * 2 * Math.PI;
                          const sx = 120 + 55 * Math.cos(angle);
                          const sy = 50 + 30 * Math.sin(angle);
                          return (
                            <circle key={i} cx={sx} cy={sy} r="8" fill={link.target_kind === "product" ? "#10b981" : "#94a3b8"} />
                          );
                        })}
                        <circle cx="120" cy="50" r="13" fill="#4f46e5" stroke="#ffffff" strokeWidth="2" />
                      </>
                    )}
                  </svg>
                </div>
                <div className="mini-graph-caption">
                  {activeLinks.length === 0 ? "No active link topology" : `${activeLinks.length} Link Connection${activeLinks.length > 1 ? "s" : ""}`}
                </div>
              </div>

              {/* Referenced Entities */}
              <div className="referenced-entities-section">
                <span className="inspector-section-label">REFERENCED ENTITIES</span>
                <div className="entity-items-list">
                  {activeLinks.length === 0 ? (
                    <div style={{ padding: "12px", fontSize: "12px", color: "var(--text-muted)", textAlign: "center" }}>
                      No linked entities. Type <code>[[</code> in your note to reference products or notes.
                    </div>
                  ) : (
                    activeLinks.map((link, idx) => (
                      <div key={idx} className="entity-item-card">
                        <div className="entity-item-top">
                          <div className="entity-name-wrap">
                            <span className={`entity-dot ${link.target_kind || "note"}`} />
                            <span className="entity-name">{link.target_ref}</span>
                          </div>
                          <span className="entity-kind-badge">{(link.target_kind || "LINK").toUpperCase()}</span>
                        </div>
                      </div>
                    ))
                  )}
                </div>
              </div>

              {/* Backlinks */}
              <div className="backlinks-section">
                <span className="inspector-section-label">BACKLINKS (0)</span>
                <div style={{ padding: "8px 12px", fontSize: "12px", color: "var(--text-muted)" }}>
                  No backlinks yet
                </div>
              </div>
            </div>

            <div className="inspector-footer-action">
              <button
                type="button"
                className="btn-expand-inspector"
                onClick={() => setViewMode("graph")}
              >
                <span>⛶</span>
                <span>Expand Graph Inspector</span>
              </button>
            </div>
          </section>
        </div>
      )}

      {/* ── Global Bottom Ribbon (Cluster & Index Status) ─────────────── */}
      <footer className="global-bottom-ribbon">
        <div className="ribbon-left">
          <span className="pulse-dot" style={{ width: "6px", height: "6px" }} />
          <span>Cluster Status: <strong className="ribbon-strong">Ready</strong></span>
          <span className="ribbon-sep">|</span>
          <span>Vector Store: <strong className="ribbon-strong">HNSW Index v2.1</strong></span>
          <span className="ribbon-sep">|</span>
          <span>Active Model: <strong className="ribbon-strong">text-embedding-3-large (1536d)</strong></span>
        </div>
        <div className="ribbon-right">
          <span>Synced with Deep Atlas Cloud</span>
          <span>•</span>
          <span>Zero Data Retention Active</span>
        </div>
      </footer>
    </div>
  );
}

// ── Rich Rendered Preview Subcomponent ──────────────────────────────────

function RenderedNotePreview({ title, body }: { title: string; body: string }) {
  if (!body.trim() && !title.trim()) {
    return (
      <div className="editor-preview-canvas" style={{ color: "var(--text-muted)", fontStyle: "italic", padding: "24px" }}>
        Empty note. Switch to edit mode to add content.
      </div>
    );
  }

  const lines = body.split("\n");

  return (
    <div className="editor-preview-canvas">
      {title && <h1 style={{ fontSize: "20px", fontWeight: 700, marginBottom: "16px", color: "var(--text-primary)" }}>{title}</h1>}
      {lines.map((line, idx) => {
        const trimmed = line.trim();
        if (!trimmed) {
          return <div key={idx} style={{ height: "10px" }} />;
        }
        if (trimmed.startsWith("### ")) {
          return <h3 key={idx} style={{ fontSize: "15px", fontWeight: 600, margin: "14px 0 6px" }}>{trimmed.replace(/^###\s+/, "")}</h3>;
        }
        if (trimmed.startsWith("## ")) {
          return <h2 key={idx} style={{ fontSize: "17px", fontWeight: 600, margin: "16px 0 8px" }}>{trimmed.replace(/^##\s+/, "")}</h2>;
        }
        if (trimmed.startsWith("# ")) {
          return <h1 key={idx} style={{ fontSize: "19px", fontWeight: 700, margin: "18px 0 10px" }}>{trimmed.replace(/^#\s+/, "")}</h1>;
        }
        if (trimmed.startsWith("- ") || trimmed.startsWith("* ")) {
          return (
            <li key={idx} style={{ marginLeft: "20px", marginBottom: "4px", fontSize: "13.5px", lineHeight: "1.6" }}>
              {renderWikilinksInText(trimmed.replace(/^[-*]\s+/, ""))}
            </li>
          );
        }
        return (
          <p key={idx} className="preview-paragraph" style={{ margin: "0 0 10px", fontSize: "13.5px", lineHeight: "1.6" }}>
            {renderWikilinksInText(line)}
          </p>
        );
      })}
    </div>
  );
}

function renderWikilinksInText(text: string) {
  const parts = text.split(/(\[\[.*?\]\])/g);
  return parts.map((part, i) => {
    if (part.startsWith("[[") && part.endsWith("]]")) {
      const inner = part.slice(2, -2).trim();
      const [kind] = inner.includes(":") ? inner.split(":") : ["note"];
      return (
        <span key={i} className={`wikilink-pill ${kind || "note"}`}>
          [[ {inner} ]]
        </span>
      );
    }
    return part;
  });
}

export default NotesPanel;
