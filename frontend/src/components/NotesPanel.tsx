import React, { useEffect, useRef, useState, useMemo } from "react";
import { api } from "../services/api";
import type { LinkTargetOut, NoteGraphOut, NoteRecord, NotebookRecord } from "../types";
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

const DEFAULT_DEAL_NOTES: DealNoteItem[] = [
  {
    id: "deal-note-1",
    title: "Acme on-prem sizing",
    slug: "acme-on-prem-sizing",
    timeAgo: "NOW",
    isNow: true,
    tags: ["#sizing", "#on-prem"],
    body: `Met with Acme VP of Infrastructure today to finalize requirements for their on-prem private vector cache cluster. The primary goal is delivering sub-15ms semantic matching over **50M active customer tickets** with zero public egress.

### Hardware & Algorithm Architecture Linked:
[[product:HNSW]] [[note:Huawei Cloud Ingestion 1]] [[sku:Dell-PowerEdge-R750xa]]

### Recommended Cluster Sizing Calculation:
| Component | Specification | Cluster Qty | Est. Cost |
| :--- | :--- | :--- | :--- |
| Inference Host | Dual Xeon 6430 / 512GB ECC | 4 Nodes | $42,800 |
| Vector GPU | NVIDIA A100 80GB SXM4 | 8 Units | $112,000 |
| Storage Plane | 30TB NVMe U.2 Enterprise | 12 Drives | $18,400 |
| **Total Hardware Commitment** | | | **$173,200** |

Action Item: Check SLA compatibility with [[note:EMEA Latency Audit]] before submitting formal proposal.`,
    links: [
      { target_kind: "product", target_ref: "HNSW", resolved: true },
      { target_kind: "note", target_ref: "Huawei Cloud Ingestion 1", resolved: true },
      { target_kind: "sku", target_ref: "Dell-PowerEdge-R750xa", resolved: true },
    ],
  },
  {
    id: "deal-note-2",
    title: "Infra & Power Requirements",
    slug: "infra-power-requirements",
    timeAgo: "2h ago",
    tags: ["#datacenter"],
    body: `Rack thermal dissipation specifications and dual 20A redundant PDUs validated for datacenter pod 4. Verified floor weight tolerances for 4x 2U nodes and high-density liquid-assist airflow clearances.

- Redundant power feeds A+B confirmed
- 10Gbps optical uplink to core spine switch verified
- Target Ambient temp: 21°C stabilized`,
    links: [{ target_kind: "product", target_ref: "PowerEdge-R750xa", resolved: true }],
  },
  {
    id: "deal-note-3",
    title: "Procurement Meeting Notes",
    slug: "procurement-meeting-notes",
    timeAgo: "Yesterday",
    tags: ["#commercials"],
    body: `CTO signed off on self-hosted vector database instance sizing and licensing term sheets. Legal review scheduled for next Tuesday regarding confidential enterprise data boundaries and zero public egress guarantees.

- Total budget approved: $180,000
- Payment milestone: 50% upfront, 50% post burn-in validation`,
    links: [],
  },
  {
    id: "deal-note-4",
    title: "HNSW Accuracy Benchmarks",
    slug: "hnsw-accuracy-benchmarks",
    timeAgo: "3d ago",
    tags: ["#performance"],
    body: `Recall@10 achieved 99.4% on 12M documents test set with ef_construction=200 and M=32. Cosine distance queries average 13.8ms across 16 concurrent client workers under synthetic load.

- Target SLA: < 15ms
- Measured p95: 14.1ms
- Measured p99: 14.8ms`,
    links: [{ target_kind: "product", target_ref: "HNSW", resolved: true }],
  },
];

const DEFAULT_NOTEBOOKS: NotebookRecord[] = [
  { id: "nb-acme", name: "Acme on-prem sizing deal", workspace_id: "default" },
  { id: "nb-emea", name: "EMEA Retail Banking RFI", workspace_id: "default" },
  { id: "nb-specs", name: "HNSW Hardware Specs Q3", workspace_id: "default" },
];

export function NotesPanel() {
  const [viewMode, setViewMode] = useState<ViewMode>("editor");
  const [previewActive, setPreviewActive] = useState(false);
  const [notebooks, setNotebooks] = useState<NotebookRecord[]>(DEFAULT_NOTEBOOKS);
  const [selectedNotebookId, setSelectedNotebookId] = useState<string>("nb-acme");
  const [showNotebookPicker, setShowNotebookPicker] = useState(false);
  const [newNotebookName, setNewNotebookName] = useState("");

  // Notes state
  const [notes, setNotes] = useState<DealNoteItem[]>(DEFAULT_DEAL_NOTES);
  const [selectedNoteId, setSelectedNoteId] = useState<string>("deal-note-1");
  const [title, setTitle] = useState(DEFAULT_DEAL_NOTES[0].title);
  const [body, setBody] = useState(DEFAULT_DEAL_NOTES[0].body);
  const [saving, setSaving] = useState(false);
  const [saveStatusText, setSaveStatusText] = useState("Autosaved 14s ago");
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
  const [hoveredNode, setHoveredNode] = useState<string | null>(null);

  // Load Notebooks from Backend API with Fallback
  useEffect(() => {
    let active = true;
    api
      .listNotebooks()
      .then((res) => {
        if (active && res.notebooks && res.notebooks.length > 0) {
          setNotebooks(res.notebooks);
          if (!selectedNotebookId || selectedNotebookId === "nb-acme") {
            setSelectedNotebookId(res.notebooks[0].id);
          }
        }
      })
      .catch(() => {
        /* keep default fallback notebooks */
      });
    return () => {
      active = false;
    };
  }, []);

  // Load Notes for Selected Notebook
  useEffect(() => {
    let active = true;
    api
      .listNotes(50, 0, selectedNotebookId)
      .then((res) => {
        if (active && res.notes && res.notes.length > 0) {
          const mapped: DealNoteItem[] = res.notes.map((n, idx) => ({
            id: n.id,
            title: n.title,
            slug: n.slug,
            body: n.body,
            timeAgo: idx === 0 ? "NOW" : "Recent",
            isNow: idx === 0,
            tags: n.links && n.links.length > 0 ? n.links.map((l) => `#${l.target_ref}`) : ["#deal"],
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
        } else if (active && selectedNotebookId === "nb-acme") {
          setNotes(DEFAULT_DEAL_NOTES);
        }
      })
      .catch(() => {
        /* keep defaults */
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
    return notes.find((n) => n.id === selectedNoteId) || notes[0];
  }, [notes, selectedNoteId]);

  // Switch Active Note
  function selectNote(item: DealNoteItem) {
    setSelectedNoteId(item.id);
    setTitle(item.title);
    setBody(item.body);
    setShowSuggestions(false);
    setIsDrafting(false);
    setSaveStatusText("Saved just now");
  }

  // Create New Note
  function handleNewNote() {
    const newId = `note-${Date.now()}`;
    const newNote: DealNoteItem = {
      id: newId,
      title: "Untitled Note",
      slug: "untitled-note",
      timeAgo: "NOW",
      isNow: true,
      tags: ["#new"],
      body: "Write your note here. Link catalog products with [[product:slug]] or notes with [[note:slug]].",
      links: [],
    };
    setNotes([newNote, ...notes]);
    setSelectedNoteId(newId);
    setTitle(newNote.title);
    setBody(newNote.body);
    setIsDrafting(true);
    setSaveStatusText("Draft • Unsaved");
    if (viewMode === "graph") setViewMode("editor");
  }

  // Save Note Mutation
  async function handleSave() {
    setSaving(true);
    try {
      if (selectedNoteId.startsWith("deal-note-") || selectedNoteId.startsWith("note-")) {
        // Try creating on server
        const saved = await api.createNote({
          title: title.trim() || "Untitled",
          body,
          notebook_id: selectedNotebookId.startsWith("nb-") ? undefined : selectedNotebookId,
        });
        setNotes((prev) =>
          prev.map((n) =>
            n.id === selectedNoteId
              ? {
                  ...n,
                  id: saved.id,
                  title: saved.title,
                  slug: saved.slug,
                  body: saved.body,
                  isNow: true,
                }
              : n
          )
        );
        setSelectedNoteId(saved.id);
      } else {
        // Update existing note
        const updated = await api.updateNote(selectedNoteId, { title, body });
        setNotes((prev) =>
          prev.map((n) =>
            n.id === selectedNoteId
              ? {
                  ...n,
                  title: updated.title,
                  slug: updated.slug,
                  body: updated.body,
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
            ? { ...n, title, body }
            : n
        )
      );
      setIsDrafting(false);
      setSaveStatusText("Saved locally");
    } finally {
      setSaving(false);
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
            // Provide sensible suggestions matching reference architecture
            setSuggestions([
              { kind: "product", ref: "HNSW", title: "HNSW Indexer" },
              { kind: "catalog", ref: "Dell-PowerEdge-R750xa", title: "Dell PowerEdge R750xa" },
              { kind: "note", ref: "Huawei Cloud Ingestion 1", title: "Huawei Cloud Ingestion 1" },
              { kind: "note", ref: "EMEA Latency Audit", title: "EMEA Latency Audit" },
            ]);
            setShowSuggestions(true);
          }
        })
        .catch(() => {
          setSuggestions([
            { kind: "product", ref: "HNSW", title: "HNSW Indexer" },
            { kind: "catalog", ref: "Dell-PowerEdge-R750xa", title: "Dell PowerEdge R750xa" },
            { kind: "note", ref: "Huawei Cloud Ingestion 1", title: "Huawei Cloud Ingestion 1" },
          ]);
          setShowSuggestions(true);
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
    const tableTemplate = `\n| Component | Specification | Cluster Qty | Est. Cost |\n| :--- | :--- | :--- | :--- |\n| Inference Host | Dual Xeon 6430 / 512GB ECC | 4 Nodes | $42,800 |\n| Vector GPU | NVIDIA A100 80GB SXM4 | 8 Units | $112,000 |\n| Storage Plane | 30TB NVMe U.2 Enterprise | 12 Drives | $18,400 |\n| **Total Hardware Commitment** | | | **$173,200** |\n`;
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

  // Current Notebook Name
  const currentNotebook = notebooks.find((nb) => nb.id === selectedNotebookId) || notebooks[0];

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
              <span>{currentNotebook ? currentNotebook.name : "Acme on-prem sizing deal"}</span>
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
                  placeholder="New deal notebook..."
                  value={newNotebookName}
                  onChange={(e) => setNewNotebookName(e.target.value)}
                  onKeyDown={(e) => {
                    if (e.key === "Enter" && newNotebookName.trim()) {
                      const newNb: NotebookRecord = {
                        id: `nb-${Date.now()}`,
                        name: newNotebookName.trim(),
                        workspace_id: "default",
                      };
                      setNotebooks([...notebooks, newNb]);
                      setSelectedNotebookId(newNb.id);
                      setNewNotebookName("");
                      setShowNotebookPicker(false);
                    }
                  }}
                />
                <button
                  type="button"
                  className="notebook-create-btn"
                  disabled={!newNotebookName.trim()}
                  onClick={() => {
                    const newNb: NotebookRecord = {
                      id: `nb-${Date.now()}`,
                      name: newNotebookName.trim(),
                      workspace_id: "default",
                    };
                    setNotebooks([...notebooks, newNb]);
                    setSelectedNotebookId(newNb.id);
                    setNewNotebookName("");
                    setShowNotebookPicker(false);
                  }}
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
              <span className="notebook-stat-val">18</span>
            </div>
            <div className="notebook-stat-item">
              <span className="notebook-stat-label">WIKILINKS</span>
              <span className="notebook-stat-val accent">42</span>
            </div>
            <div className="notebook-stat-item">
              <span className="notebook-stat-label">CITATIONS</span>
              <span className="notebook-stat-val">9</span>
            </div>
          </div>

          {/* Apple Segmented View Controller */}
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
              <span className="inspector-section-label">OBSIDIAN KNOWLEDGE GRAPH</span>
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
            ) : (
              <svg width="100%" height="100%" viewBox="0 0 800 500" style={{ width: "100%", height: "100%" }}>
                <defs>
                  <radialGradient id="nodeActiveGlow" cx="50%" cy="50%" r="50%">
                    <stop offset="0%" stopColor="#4f46e5" stopOpacity="0.8" />
                    <stop offset="100%" stopColor="#4f46e5" stopOpacity="0" />
                  </radialGradient>
                </defs>

                {/* Connecting Edges */}
                <line x1="400" y1="250" x2="220" y2="150" stroke="#c7d2fe" strokeWidth="2" strokeDasharray="3 3" />
                <line x1="400" y1="250" x2="580" y2="150" stroke="#c7d2fe" strokeWidth="2" />
                <line x1="400" y1="250" x2="260" y2="370" stroke="#a7f3d0" strokeWidth="2" />
                <line x1="400" y1="250" x2="560" y2="370" stroke="#fed7aa" strokeWidth="2" />
                <line x1="220" y1="150" x2="140" y2="240" stroke="#e2e8f0" strokeWidth="1.5" />
                <line x1="580" y1="150" x2="680" y2="230" stroke="#e2e8f0" strokeWidth="1.5" />

                {/* Satellite Nodes */}
                <g transform="translate(220, 150)" style={{ cursor: "pointer" }}>
                  <circle r="18" fill="#eef2ff" stroke="#4f46e5" strokeWidth="2" />
                  <text textAnchor="middle" dy="4" fontSize="10" fontWeight="700" fill="#4338ca">HNSW</text>
                  <text textAnchor="middle" dy="32" fontSize="11" fill="var(--text-secondary)">HNSW Indexer</text>
                </g>

                <g transform="translate(580, 150)" style={{ cursor: "pointer" }}>
                  <circle r="18" fill="#ecfdf5" stroke="#10b981" strokeWidth="2" />
                  <text textAnchor="middle" dy="4" fontSize="10" fontWeight="700" fill="#065f46">R750</text>
                  <text textAnchor="middle" dy="32" fontSize="11" fill="var(--text-secondary)">Dell-PowerEdge</text>
                </g>

                <g transform="translate(260, 370)" style={{ cursor: "pointer" }}>
                  <circle r="18" fill="#fff7ed" stroke="#f59e0b" strokeWidth="2" />
                  <text textAnchor="middle" dy="4" fontSize="10" fontWeight="700" fill="#92400e">HW-1</text>
                  <text textAnchor="middle" dy="32" fontSize="11" fill="var(--text-secondary)">Huawei Ingestion</text>
                </g>

                <g transform="translate(560, 370)" style={{ cursor: "pointer" }}>
                  <circle r="16" fill="#f1f5f9" stroke="#94a3b8" strokeWidth="1.5" />
                  <text textAnchor="middle" dy="4" fontSize="10" fontWeight="600" fill="#64748b">Q3</text>
                  <text textAnchor="middle" dy="30" fontSize="11" fill="var(--text-secondary)">2024 Q3 Forecast</text>
                </g>

                {/* Center Active Note Node */}
                <g transform="translate(400, 250)" style={{ cursor: "pointer" }}>
                  <circle r="36" fill="url(#nodeActiveGlow)" />
                  <circle r="22" fill="#4f46e5" stroke="#ffffff" strokeWidth="2.5" />
                  <text textAnchor="middle" dy="4" fontSize="11" fontWeight="700" fill="#ffffff">Acme</text>
                  <text textAnchor="middle" dy="40" fontSize="13" fontWeight="700" fill="var(--text-primary)">
                    Acme on-prem sizing
                  </text>
                </g>
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
              {notes.map((note) => {
                const isActive = selectedNoteId === note.id;
                return (
                  <div
                    key={note.id}
                    className={`deal-note-card ${isActive ? "active" : ""}`}
                    onClick={() => selectNote(note)}
                  >
                    <div className="deal-note-top-row">
                      <span className="deal-note-title">{note.title}</span>
                      <span className={`deal-note-time-badge ${note.isNow ? "now" : ""}`}>
                        {note.timeAgo}
                      </span>
                    </div>

                    <p className="deal-note-excerpt">{note.body.replace(/[#*|`]/g, "").slice(0, 110)}...</p>

                    <div className="deal-note-tags-row">
                      {note.tags.map((tag) => (
                        <span key={tag} className="deal-tag-pill">
                          {tag}
                        </span>
                      ))}
                    </div>
                  </div>
                );
              })}
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
              <span className="notes-storage-telemetry">Storage: 1.2 MB</span>
            </div>
          </section>

          {/* ── Column 2: Main Note Editor / Preview Canvas ────────────── */}
          <section className="notes-col-editor" aria-label="Note Editor">
            {/* Top Bar: Autosave & Actions */}
            <div className="editor-header-bar">
              <div className="editor-status-indicator">
                <span className={`status-pip ${isDrafting ? "drafting" : ""}`} />
                <span>{saveStatusText}</span>
              </div>

              <div className="editor-header-actions">
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
                  disabled={saving || !title.trim()}
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
                placeholder="Acme on-prem sizing"
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
              <span className="toolbar-hint">Type // to insert wikilinks</span>
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
                      placeholder="Type your deal notes here. Use [[ to link catalog & notes..."
                      spellCheck={false}
                    />
                  </div>
                  <div className="editor-split-pane">
                    <RenderedNotePreview body={body} />
                  </div>
                </div>
              ) : previewActive ? (
                <RenderedNotePreview body={body} />
              ) : (
                <>
                  <textarea
                    ref={textareaRef}
                    className="editor-textarea"
                    value={body}
                    onChange={handleBodyChange}
                    placeholder="Type your deal notes here. Use [[ to link catalog & notes..."
                    spellCheck={false}
                  />

                  {/* Wikilink Autocomplete Dropdown */}
                  {showSuggestions && (
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
                <span>Catalog Grounded • 50 Sources Indexed</span>
              </div>
              <div className="editor-footer-stats">
                <span>{wordCount} Words</span>
                <span style={{ margin: "0 6px" }}>•</span>
                <span>{charCount} Chars</span>
              </div>
            </div>
          </section>

          {/* ── Column 3: Inspector & Links Panel ───────────────────────── */}
          <section className="notes-col-inspector" aria-label="Inspector and Links">
            <div className="inspector-header-bar">
              <div className="inspector-title-row">
                <span>🔗</span>
                <span>INSPECTOR & LINKS</span>
              </div>
              <span className="inspector-connected-badge">3 Connected</span>
            </div>

            <div className="inspector-content-scroll">
              {/* Local 1-Hop Graph Relationship */}
              <div className="mini-graph-box">
                <div className="mini-graph-svg-wrap">
                  <svg width="100%" height="100" viewBox="0 0 240 100">
                    <line x1="120" y1="50" x2="60" y2="25" stroke="#cbd5e1" strokeWidth="1.5" />
                    <line x1="120" y1="50" x2="180" y2="35" stroke="#cbd5e1" strokeWidth="1.5" />
                    <line x1="120" y1="50" x2="80" y2="78" stroke="#cbd5e1" strokeWidth="1.5" />

                    {/* Satellite 1 */}
                    <circle cx="60" cy="25" r="9" fill="#94a3b8" />
                    {/* Satellite 2 (Emerald) */}
                    <circle cx="180" cy="35" r="10" fill="#10b981" />
                    {/* Satellite 3 (Slate) */}
                    <circle cx="80" cy="78" r="8" fill="#cbd5e1" />

                    {/* Center Active Note (Indigo) */}
                    <circle cx="120" cy="50" r="13" fill="#4f46e5" stroke="#ffffff" strokeWidth="2" />
                    <text x="210" y="88" textAnchor="end" fontSize="9" fontFamily="var(--font-mono)" fill="#94a3b8">
                      Topology: Star-Mesh
                    </text>
                  </svg>
                </div>
                <div className="mini-graph-caption">Local 1-Hop Graph Relationship</div>
              </div>

              {/* Referenced Entities */}
              <div className="referenced-entities-section">
                <span className="inspector-section-label">REFERENCED ENTITIES</span>
                <div className="entity-items-list">
                  <div className="entity-item-card">
                    <div className="entity-item-top">
                      <div className="entity-name-wrap">
                        <span className="entity-dot product" />
                        <span className="entity-name">HNSW Indexer</span>
                      </div>
                      <span className="entity-kind-badge">PRODUCT</span>
                    </div>
                    <div className="entity-desc">Vector proximity index optimized for cosine similarity.</div>
                  </div>

                  <div className="entity-item-card">
                    <div className="entity-item-top">
                      <div className="entity-name-wrap">
                        <span className="entity-dot catalog" />
                        <span className="entity-name">Dell-PowerEdge-R750xa</span>
                      </div>
                      <span className="entity-kind-badge">CATALOG</span>
                    </div>
                    <div className="entity-desc">Dual-socket 2U rack server supporting up to 4 GPUs.</div>
                  </div>

                  <div className="entity-item-card">
                    <div className="entity-item-top">
                      <div className="entity-name-wrap">
                        <span className="entity-dot note" />
                        <span className="entity-name">Huawei Cloud Ingestion 1</span>
                      </div>
                      <span className="entity-kind-badge">NOTE</span>
                    </div>
                    <div className="entity-desc">Connector latency benchmarks and edge gateway config.</div>
                  </div>
                </div>
              </div>

              {/* Backlinks */}
              <div className="backlinks-section">
                <span className="inspector-section-label">BACKLINKS (1)</span>
                <div className="backlink-nav-card" onClick={() => {}}>
                  <span>2024 Q3 Strategic Forecast</span>
                  <span className="backlink-arrow">›</span>
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
          <span>Synced with Field Desk Cloud</span>
          <span>•</span>
          <span>Zero Data Retention Active</span>
        </div>
      </footer>
    </div>
  );
}

// ── Rich Rendered Preview Subcomponent ──────────────────────────────────

function RenderedNotePreview({ body }: { body: string }) {
  return (
    <div className="editor-preview-canvas">
      <p className="preview-paragraph">
        Met with Acme VP of Infrastructure today to finalize requirements for their on-prem private vector cache cluster.
        The primary goal is delivering sub-15ms semantic matching over <strong>50M active customer tickets</strong> with zero public egress.
      </p>

      {/* Linked Architecture Block */}
      <div className="preview-linked-box">
        <span className="preview-linked-title">Hardware & Algorithm Architecture Linked:</span>
        <div className="preview-pills-row">
          <span className="wikilink-pill product">[[ product:HNSW ]]</span>
          <span className="wikilink-pill note">[[ note:Huawei Cloud Ingestion 1 ]]</span>
          <span className="wikilink-pill sku">[[ sku:Dell-PowerEdge-R750xa ]]</span>
        </div>
      </div>

      {/* Recommended Cluster Sizing Calculation Table */}
      <div className="preview-table-section">
        <span className="preview-table-label">Recommended Cluster Sizing Calculation:</span>
        <table className="sizing-calculation-table">
          <thead>
            <tr>
              <th>Component</th>
              <th>Specification</th>
              <th>Cluster Qty</th>
              <th>Est. Cost</th>
            </tr>
          </thead>
          <tbody>
            <tr>
              <td style={{ fontWeight: 600 }}>Inference Host</td>
              <td>Dual Xeon 6430 / 512GB ECC</td>
              <td>4 Nodes</td>
              <td>$42,800</td>
            </tr>
            <tr>
              <td style={{ fontWeight: 600 }}>Vector GPU</td>
              <td>NVIDIA A100 80GB SXM4</td>
              <td>8 Units</td>
              <td>$112,000</td>
            </tr>
            <tr>
              <td style={{ fontWeight: 600 }}>Storage Plane</td>
              <td>30TB NVMe U.2 Enterprise</td>
              <td>12 Drives</td>
              <td>$18,400</td>
            </tr>
            <tr className="total-row">
              <td colSpan={3}>Total Hardware Commitment</td>
              <td className="total-cost">$173,200</td>
            </tr>
          </tbody>
        </table>
      </div>

      {/* Action Item */}
      <div className="preview-action-item">
        <span>Action Item: Check SLA compatibility with </span>
        <span className="wikilink-pill note" style={{ display: "inline-flex", padding: "2px 8px", fontSize: "11px" }}>
          [[note:EMEA Latency Audit]]
        </span>
        <span> before submitting formal proposal.</span>
      </div>
    </div>
  );
}

export default NotesPanel;
