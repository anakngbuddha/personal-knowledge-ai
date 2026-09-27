import React, { ChangeEvent, DragEvent, useEffect, useMemo, useRef, useState } from "react";
import { AssistantMarkdown } from "./AssistantMarkdown";
import {
  ActivityIcon,
  CheckIcon,
  DatabaseIcon,
  ExternalLinkIcon,
  FileTextIcon,
  FilterIcon,
  FolderIcon,
  GridIcon,
  InfoIcon,
  LayersVectorIcon,
  ListIcon,
  RefreshCwIcon,
  SearchIcon,
  SparkleSquircleIcon,
  StarIcon,
  TrashIcon,
  UploadCloudIcon,
  ZapIcon,
} from "./Icons";
import { api } from "../services/api";
import type {
  DocumentChunk,
  FreshnessAlert,
  GraphEdge,
  KnowledgeDocument,
  SearchHit,
  SearchResponse,
  StudioResult,
  TrackedUpload,
  UploadPhase,
  VendorSource,
} from "../types";

type Tab = "sources" | "ask" | "notes" | "map" | "connections" | "settings";

export interface TabItem {
  id: Tab;
  name: string;
  icon: React.ComponentType<{ size?: number }>;
  badge?: string;
}

interface Props {
  documents: KnowledgeDocument[];
  loading: boolean;
  error: string | null;
  refresh: () => void;
  setError: (msg: string | null) => void;
  selectedId: string | null;
  onSelect: (id: string | null) => void;
  onNavigate: (tab: "ask" | "map" | "notes" | "connections" | "settings", prompt?: string) => void;
  activeTab?: Tab;
  onTabChange?: (tab: Tab) => void;
  tabs?: TabItem[];
}

type PerspectiveMode = "library" | "passages" | "watches";
type ViewMode = "grid" | "list";
type InspectorSubTab = "insights" | "passages" | "studio";

const ACCEPT = ".pdf,.docx,.pptx,.xlsx,.txt,.md,.html";
const POLL_MS = 2000;

const PHASE_LABEL: Record<UploadPhase, string> = {
  queued: "Waiting",
  reading: "Reading the file",
  understanding: "Working out what it says",
  ready: "Ready to ask about",
  failed: "Could not be added",
};

let counter = 0;
function nextKey(): string {
  counter += 1;
  return `u${counter}`;
}

function formatSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(0)} KB`;
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`;
}

function getFileFormatMeta(filename: string): { label: string; color: string; bg: string } {
  const ext = filename.split(".").pop()?.toLowerCase() || "";
  switch (ext) {
    case "pdf":
      return { label: "PDF", color: "#ef4444", bg: "rgba(239, 68, 68, 0.12)" };
    case "docx":
    case "doc":
      return { label: "WORD", color: "#3b82f6", bg: "rgba(59, 130, 246, 0.12)" };
    case "xlsx":
    case "xls":
    case "csv":
      return { label: "SHEET", color: "#10b981", bg: "rgba(16, 185, 129, 0.12)" };
    case "pptx":
    case "ppt":
      return { label: "SLIDES", color: "#f59e0b", bg: "rgba(245, 158, 11, 0.12)" };
    case "md":
    case "markdown":
      return { label: "MD", color: "#8b5cf6", bg: "rgba(139, 92, 246, 0.12)" };
    case "html":
    case "htm":
      return { label: "WEB", color: "#06b6d4", bg: "rgba(6, 182, 212, 0.12)" };
    default:
      return { label: ext.toUpperCase() || "DOC", color: "#64748b", bg: "rgba(100, 116, 139, 0.12)" };
  }
}

const RELATION_WORDS: Record<string, string> = {
  compatible: "works with",
  incompatible: "does not work with",
  conflicts_with: "clashes with",
  requires: "needs",
  replaces: "replaces",
  supersedes: "replaces",
  bundled_with: "is sold together with",
  recommended_with: "is recommended with",
  cross_sell: "pairs well with",
  upsell_to: "is a step up to",
  certified_for: "is certified for",
  requires_license: "needs a licence for",
  bundle_component: "is part of",
  suits_use_case: "suits",
};

export function SourcesWorkspace({
  documents,
  loading,
  error,
  refresh,
  setError,
  selectedId,
  onSelect,
  onNavigate,
  activeTab = "sources",
  onTabChange,
  tabs,
}: Props) {
  // Perspective & View Mode State
  const [perspective, setPerspective] = useState<PerspectiveMode>("library");
  const [viewMode, setViewMode] = useState<ViewMode>("grid");
  const [uploaderExpanded, setUploaderExpanded] = useState(true);

  // Search & Filter State
  const [searchQuery, setSearchQuery] = useState("");
  const [statusFilter, setStatusFilter] = useState<string>("all");
  const [formatFilter, setFormatFilter] = useState<string>("all");
  const [vendorFilter, setVendorFilter] = useState<string>("all");

  // Upload Tracking State
  const [uploadItems, setUploadItems] = useState<TrackedUpload[]>([]);
  const [uploadBusy, setUploadBusy] = useState(false);
  const [dragging, setDragging] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const folderInputRef = useRef<HTMLInputElement>(null);

  // Inspector State
  const [inspectorTab, setInspectorTab] = useState<InspectorSubTab>("insights");
  const [selectedDoc, setSelectedDoc] = useState<KnowledgeDocument | null>(null);
  const [docChunks, setDocChunks] = useState<DocumentChunk[]>([]);
  const [chunksLoading, setChunksLoading] = useState(false);
  const [suggestions, setSuggestions] = useState<GraphEdge[]>([]);
  const [inspectorLoading, setInspectorLoading] = useState(false);
  const [pendingDeleteId, setPendingDeleteId] = useState<string | null>(null);

  // Inline Edit State
  const [editing, setEditing] = useState(false);
  const [savingEdit, setSavingEdit] = useState(false);
  const [summaryDraft, setSummaryDraft] = useState("");
  const [vendorDraft, setVendorDraft] = useState("");
  const [productsDraft, setProductsDraft] = useState("");
  const [validUntilDraft, setValidUntilDraft] = useState("");

  // Studio State
  const [suggestedQuestions, setSuggestedQuestions] = useState<string[]>([]);
  const [studioResult, setStudioResult] = useState<StudioResult | null>(null);
  const [studioBusy, setStudioBusy] = useState(false);

  // Passage Search State (Perspective 2)
  const [passageQuery, setPassageQuery] = useState("");
  const [passageApprovedOnly, setPassageApprovedOnly] = useState(true);
  const [passageExcludeInjection, setPassageExcludeInjection] = useState(true);
  const [passageLoading, setPassageLoading] = useState(false);
  const [passageResult, setPassageResult] = useState<SearchResponse | null>(null);
  const [expandedChunkId, setExpandedChunkId] = useState<string | null>(null);

  // Web Watches State (Perspective 3)
  const [watchSources, setWatchSources] = useState<VendorSource[]>([]);
  const [watchAlerts, setWatchAlerts] = useState<FreshnessAlert[]>([]);
  const [watchLabel, setWatchLabel] = useState("");
  const [watchUrl, setWatchUrl] = useState("");
  const [watchBusy, setWatchBusy] = useState(false);
  const [watchMessage, setWatchMessage] = useState<string | null>(null);

  // Setup folder picker attribute
  useEffect(() => {
    const el = folderInputRef.current;
    if (!el) return;
    el.setAttribute("webkitdirectory", "");
    el.setAttribute("directory", "");
  }, []);

  // Poll pending uploads
  useEffect(() => {
    const pending = uploadItems.filter(
      (item) => item.documentId && item.phase !== "ready" && item.phase !== "failed"
    );
    if (pending.length === 0) return;

    const timer = setTimeout(async () => {
      const updates = await Promise.all(
        pending.map(async (item) => {
          try {
            const report = await api.documentStatus(item.documentId as string);
            let phase: UploadPhase = "queued";
            if (report.status === "ready") phase = "ready";
            else if (report.status === "failed" || report.status === "quarantined") phase = "failed";
            else if (report.status === "processing") phase = report.chunk_count > 0 ? "understanding" : "reading";
            return { key: item.key, phase, detail: report.error_message };
          } catch {
            return null;
          }
        })
      );
      let reachedReady = false;
      setUploadItems((prev) =>
        prev.map((item) => {
          const update = updates.find((u) => u && u.key === item.key);
          if (!update) return item;
          if (update.phase === "ready" && item.phase !== "ready") reachedReady = true;
          return { ...item, phase: update.phase, detail: update.detail ?? item.detail };
        })
      );
      if (reachedReady) refresh();
    }, POLL_MS);

    return () => clearTimeout(timer);
  }, [uploadItems, refresh]);

  // Load selected document details for Inspector
  useEffect(() => {
    if (!selectedId) {
      setSelectedDoc(null);
      setDocChunks([]);
      setSuggestions([]);
      setSuggestedQuestions([]);
      setStudioResult(null);
      setEditing(false);
      return;
    }

    setInspectorLoading(true);
    api
      .getDocument(selectedId)
      .then((doc) => {
        setSelectedDoc(doc);
        setSummaryDraft(doc.summary ?? "");
        setVendorDraft(doc.vendor ?? "");
        setProductsDraft((doc.products_referenced ?? []).join(", "));
        setValidUntilDraft((doc.valid_until ?? "").slice(0, 10));
      })
      .catch((err) => {
        setError(err instanceof Error ? err.message : "Could not load document details");
        setSelectedDoc(null);
      })
      .finally(() => setInspectorLoading(false));

    setChunksLoading(true);
    api
      .listChunks(selectedId)
      .then(setDocChunks)
      .catch(() => setDocChunks([]))
      .finally(() => setChunksLoading(false));

    api
      .listEdges({ status: "pending_review" })
      .then((edges) => setSuggestions(edges.filter((e) => e.document_id === selectedId)))
      .catch(() => setSuggestions([]));
  }, [selectedId, setError]);

  // Load Watches when in watches perspective
  useEffect(() => {
    if (perspective === "watches") {
      void loadWatches();
    }
  }, [perspective]);

  async function loadWatches() {
    try {
      const [src, alerts] = await Promise.all([
        api.listVendorSources(),
        api.listFreshnessAlerts(),
      ]);
      setWatchSources(src.sources);
      setWatchAlerts(alerts.alerts);
    } catch {
      /* ignore watch load errors */
    }
  }

  // Upload handler
  async function addFiles(files: File[]) {
    if (files.length === 0) return;
    const tracked: TrackedUpload[] = files.map((file) => ({
      key: nextKey(),
      filename: file.name,
      file,
      phase: "queued",
      documentId: null,
      detail: null,
    }));
    setUploadItems((prev) => [...tracked, ...prev]);
    setUploadBusy(true);
    setUploaderExpanded(true);

    try {
      const res = await api.uploadDocuments(files);
      setUploadItems((prev) =>
        prev.map((item) => {
          if (!tracked.some((t) => t.key === item.key)) return item;
          const report = res.results.find((r) => r.original_filename === item.filename);
          if (!report) return item;
          if (report.status === "rejected") {
            return { ...item, phase: "failed", detail: report.detail || "File rejected" };
          }
          if (report.status === "duplicate") {
            return { ...item, phase: "ready", detail: "Already in knowledge catalog" };
          }
          return { ...item, phase: "reading", documentId: report.document_id ?? null };
        })
      );
      refresh();
    } catch (err) {
      const message = err instanceof Error ? err.message : "Upload failed";
      setUploadItems((prev) =>
        prev.map((item) =>
          tracked.some((t) => t.key === item.key)
            ? { ...item, phase: "failed", detail: message }
            : item
        )
      );
      setError(message);
    } finally {
      setUploadBusy(false);
      if (fileInputRef.current) fileInputRef.current.value = "";
      if (folderInputRef.current) folderInputRef.current.value = "";
    }
  }

  // Document actions
  async function removeDocument(id: string) {
    try {
      await api.deleteDocument(id);
      if (selectedId === id) onSelect(null);
      refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to delete document");
    }
  }

  async function reprocessDocument(id: string) {
    try {
      await api.reprocessDocument(id);
      refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to reprocess document");
    }
  }

  // Save metadata edit
  async function handleSaveEdit() {
    if (!selectedDoc) return;
    setSavingEdit(true);
    try {
      const products = productsDraft
        .split(",")
        .map((p) => p.trim())
        .filter((p) => p.length > 0);
      const updated = await api.updateDocument(selectedDoc.id, {
        summary: summaryDraft.trim() || null,
        vendor: vendorDraft.trim() || null,
        products_referenced: products.length > 0 ? products : null,
        valid_until: validUntilDraft || null,
      });
      setSelectedDoc(updated);
      setEditing(false);
      refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not save metadata edits");
    } finally {
      setSavingEdit(false);
    }
  }

  // Edge suggestions
  async function acceptEdge(edgeId: string) {
    try {
      await api.approveEdge(edgeId);
      setSuggestions((prev) => prev.filter((e) => e.id !== edgeId));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to add to knowledge map");
    }
  }

  async function dismissEdge(edgeId: string) {
    try {
      await api.rejectEdge(edgeId, "Not right for our map");
      setSuggestions((prev) => prev.filter((e) => e.id !== edgeId));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to dismiss suggestion");
    }
  }

  // Studio Triggers
  async function runStudioQuestions() {
    if (!selectedId) return;
    setStudioBusy(true);
    try {
      const res = await api.studioQuestions(selectedId);
      setSuggestedQuestions(res.questions);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not generate questions");
    } finally {
      setStudioBusy(false);
    }
  }

  async function runStudioAction(kind: "briefing" | "faq") {
    if (!selectedId) return;
    setStudioBusy(true);
    try {
      const res = await api.studioRun({ kind, document_ids: [selectedId] });
      setStudioResult(res);
    } catch (err) {
      setError(err instanceof Error ? err.message : `Could not generate ${kind}`);
    } finally {
      setStudioBusy(false);
    }
  }

  // Passage search
  async function handlePassageSearch(e: React.FormEvent) {
    e.preventDefault();
    if (!passageQuery.trim()) return;
    setPassageLoading(true);
    try {
      const res = await api.search(passageQuery.trim(), {
        mode: "hybrid",
        filters: {
          approved_only: passageApprovedOnly,
          exclude_injection_flagged: passageExcludeInjection,
        },
      });
      setPassageResult(res);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Search failed");
    } finally {
      setPassageLoading(false);
    }
  }

  // Web Watch actions
  async function handleAddWatch(e: React.FormEvent) {
    e.preventDefault();
    if (!watchLabel.trim() || !watchUrl.trim()) return;
    setWatchBusy(true);
    setWatchMessage(null);
    try {
      await api.createVendorSource({ label: watchLabel, url: watchUrl });
      setWatchLabel("");
      setWatchUrl("");
      setWatchMessage("Source registered. The poller will crawl and hash it on schedule.");
      await loadWatches();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not add watch URL");
    } finally {
      setWatchBusy(false);
    }
  }

  async function handleCheckWatch(id: string) {
    setWatchBusy(true);
    try {
      const res = await api.checkVendorSource(id);
      setWatchMessage(
        res.status === "queued"
          ? "Crawl queued in background."
          : res.changed
            ? "Upstream content changed — staleness alert raised."
            : res.error
              ? res.error
              : `Status: ${res.status}`
      );
      await loadWatches();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Check failed");
    } finally {
      setWatchBusy(false);
    }
  }

  async function handleAckAlert(id: string) {
    try {
      await api.ackFreshnessAlert(id);
      await loadWatches();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not acknowledge alert");
    }
  }

  // Dynamic list of unique vendors for filtering
  const availableVendors = useMemo(() => {
    const set = new Set<string>();
    documents.forEach((d) => {
      if (d.vendor) set.add(d.vendor);
      if (d.detected_vendors) d.detected_vendors.forEach((v) => set.add(v));
    });
    return Array.from(set).sort();
  }, [documents]);

  // Filtered documents
  const filteredDocuments = useMemo(() => {
    return documents.filter((doc) => {
      // Query filter
      if (searchQuery.trim()) {
        const q = searchQuery.toLowerCase();
        const nameMatch = doc.original_filename.toLowerCase().includes(q);
        const titleMatch = doc.title?.toLowerCase().includes(q);
        const vendorMatch = doc.vendor?.toLowerCase().includes(q);
        const summaryMatch = doc.summary?.toLowerCase().includes(q);
        const productMatch = doc.products_referenced?.some((p) => p.toLowerCase().includes(q));
        if (!nameMatch && !titleMatch && !vendorMatch && !summaryMatch && !productMatch) {
          return false;
        }
      }
      // Status filter
      if (statusFilter !== "all" && doc.status !== statusFilter) return false;
      // Format filter
      if (formatFilter !== "all") {
        const ext = doc.original_filename.split(".").pop()?.toLowerCase();
        if (ext !== formatFilter) return false;
      }
      // Vendor filter
      if (vendorFilter !== "all") {
        if (doc.vendor !== vendorFilter && !doc.detected_vendors?.includes(vendorFilter)) {
          return false;
        }
      }
      return true;
    });
  }, [documents, searchQuery, statusFilter, formatFilter, vendorFilter]);

  // Total stats
  const totalChunksCount = useMemo(() => {
    return documents.reduce((acc, d) => acc + (d.chunk_count || 0), 0);
  }, [documents]);

  const totalPagesCount = useMemo(() => {
    return documents.reduce((acc, d) => acc + (d.page_count || 0), 0);
  }, [documents]);

  return (
    <div className="sources-desk">
      {/* ── Left Column: Workspace Navigation, Perspectives & Filters ── */}
      <aside className="sources-sources">
        {/* Workspace Tab Navigation (Matching Ask Intelligence & Knowledge Map) */}
        {tabs && onTabChange && (
          <div className="sidebar-workspace-nav">
            <div className="sidebar-section-title">WORKSPACE</div>
            <div className="workspace-tabs-list">
              {tabs.map((tab) => {
                const Icon = tab.icon;
                const isActive = activeTab === tab.id;
                return (
                  <button
                    key={tab.id}
                    type="button"
                    className={`workspace-tab-btn ${isActive ? "active" : ""}`}
                    onClick={() => onTabChange(tab.id)}
                  >
                    <span className="tab-btn-icon">
                      <Icon size={17} />
                    </span>
                    <span className="tab-btn-name">{tab.name}</span>
                    {tab.badge && (
                      <span
                        className={`tab-btn-badge ${
                          tab.badge === "Live" ? "live" : tab.badge === "AI" ? "ai" : ""
                        }`}
                      >
                        {tab.badge}
                      </span>
                    )}
                  </button>
                );
              })}
            </div>
          </div>
        )}

        {/* Perspective Mode Segmented Control */}
        <div className="sources-perspective-segment">
          <div className="sidebar-section-title">PERSPECTIVE</div>
          <div className="segmented-control">
            <button
              type="button"
              className={`segmented-item ${perspective === "library" ? "active" : ""}`}
              onClick={() => setPerspective("library")}
              title="Catalog Library & Uploads"
            >
              <FileTextIcon size={14} />
              <span>Library</span>
            </button>
            <button
              type="button"
              className={`segmented-item ${perspective === "passages" ? "active" : ""}`}
              onClick={() => setPerspective("passages")}
              title="Hybrid Vector & Passages Search"
            >
              <LayersVectorIcon size={14} />
              <span>Passages</span>
            </button>
            <button
              type="button"
              className={`segmented-item ${perspective === "watches" ? "active" : ""}`}
              onClick={() => setPerspective("watches")}
              title="Datasheet Watches & Freshness"
            >
              <ZapIcon size={14} />
              <span>Watches</span>
            </button>
          </div>
        </div>

        {/* Source Filters Card */}
        <div className="sources-setup-card sources-filters-card">
          <div className="sources-setup-header">FILTER SOURCES</div>

          {/* Search Filter Input */}
          <div className="filter-group">
            <div className="sources-filter-search">
              <SearchIcon size={13} style={{ color: "var(--text-muted)" }} />
              <input
                type="text"
                className="sources-filter-input"
                placeholder="Search sources…"
                aria-label="Search sources"
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
              />
              {searchQuery && (
                <button
                  type="button"
                  className="filter-clear-btn"
                  onClick={() => setSearchQuery("")}
                  aria-label="Clear source search"
                >
                  ×
                </button>
              )}
            </div>
          </div>

          {/* Status Filter */}
          <div className="filter-group">
            <label className="filter-label">Status</label>
            <div className="filter-chips-row">
              {["all", "ready", "processing", "failed"].map((st) => (
                <button
                  key={st}
                  type="button"
                  className={`filter-chip ${statusFilter === st ? "active" : ""}`}
                  onClick={() => setStatusFilter(st)}
                >
                  {st.charAt(0).toUpperCase() + st.slice(1)}
                </button>
              ))}
            </div>
          </div>

          {/* Format Filter */}
          <div className="filter-group">
            <label className="filter-label">Format</label>
            <div className="filter-chips-row">
              {["all", "pdf", "docx", "xlsx", "pptx", "md", "txt"].map((fmt) => (
                <button
                  key={fmt}
                  type="button"
                  className={`filter-chip ${formatFilter === fmt ? "active" : ""}`}
                  onClick={() => setFormatFilter(fmt)}
                >
                  {fmt.toUpperCase()}
                </button>
              ))}
            </div>
          </div>

          {/* Vendor Filter */}
          {availableVendors.length > 0 && (
            <div className="filter-group">
              <label className="filter-label">Vendor</label>
              <select
                className="filter-select"
                value={vendorFilter}
                onChange={(e) => setVendorFilter(e.target.value)}
              >
                <option value="all">All Vendors ({availableVendors.length})</option>
                {availableVendors.map((v) => (
                  <option key={v} value={v}>
                    {v}
                  </option>
                ))}
              </select>
            </div>
          )}

          {(searchQuery || statusFilter !== "all" || formatFilter !== "all" || vendorFilter !== "all") && (
            <button
              type="button"
              className="filter-reset-link"
              onClick={() => {
                setSearchQuery("");
                setStatusFilter("all");
                setFormatFilter("all");
                setVendorFilter("all");
              }}
            >
              Reset all filters
            </button>
          )}
        </div>

        {/* Ingestion Workflow Steps Card (Matching Ask Intelligence) */}
        <div className="sources-setup-card">
          <div className="sources-setup-header">INGESTION PIPELINE</div>
          <div className="setup-steps-list">
            <div className="setup-step-row">
              <span className="setup-step-num">1</span>
              <span className="setup-step-text">Ingest &amp; OCR documents</span>
            </div>
            <div className="setup-step-row">
              <span className="setup-step-num">2</span>
              <span className="setup-step-text">Semantic chunking &amp; HNSW</span>
            </div>
            <div className="setup-step-row">
              <span className="setup-step-num">3</span>
              <span className="setup-step-text">Grounded hybrid reasoning</span>
            </div>
          </div>
          <div className="setup-links-row">
            <button type="button" className="setup-link-blue" onClick={() => onNavigate("ask")}>
              Ask Intelligence
            </button>
            <button type="button" className="setup-link-gray" onClick={() => onNavigate("map")}>
              View Map
            </button>
          </div>
        </div>

        {/* Vector Memory Telemetry Card (Matching Ask Intelligence & Map) */}
        <div className="vector-memory-card">
          <div className="vector-memory-row">
            <div className="vector-memory-icon-wrap">
              <LayersVectorIcon size={16} />
            </div>
            <div className="vector-memory-info">
              <div className="vector-memory-title-row">
                <span className="vector-memory-title">Vector Memory</span>
                <span className="vector-memory-hnsw">HNSW</span>
              </div>
              <div className="vector-memory-meta">
                {documents.length} sources indexed &bull; isolation active
              </div>
            </div>
          </div>
          <div className="vector-memory-sub-row">
            <span>Dim: 1536 (OpenAI / ada-002)</span>
            <span style={{ color: "#10b981", fontWeight: 600 }}>Sync: OK</span>
          </div>
        </div>
      </aside>

      {/* ── Center Column: Main Interactive Workspace ────────────────── */}
      <main className="sources-main">
        {error && <div className="banner error">{error}</div>}

        {/* Top Cupertino Header Bar */}
        <header className="sources-main-header">
          <div className="sources-title-block">
            <div className="sources-title-row">
              <h1 className="sources-title">Knowledge Sources</h1>
              <span className="sources-count-pill">{documents.length} {documents.length === 1 ? "source" : "sources"}</span>
            </div>
            <p className="sources-subtitle">
              Centralized repository and semantic index for your AI workflows.
            </p>
          </div>

          <div className="sources-header-actions">
            {/* View Mode Toggle (Grid vs List) */}
            {perspective === "library" && (
              <div className="sources-view-switcher">
                <button
                  type="button"
                  className={`view-btn ${viewMode === "grid" ? "active" : ""}`}
                  onClick={() => setViewMode("grid")}
                  title="Grid cards view"
                  aria-label="Grid cards view"
                  aria-pressed={viewMode === "grid"}
                >
                  <GridIcon size={15} />
                </button>
                <button
                  type="button"
                  className={`view-btn ${viewMode === "list" ? "active" : ""}`}
                  onClick={() => setViewMode("list")}
                  title="Compact list view"
                  aria-label="Compact list view"
                  aria-pressed={viewMode === "list"}
                >
                  <ListIcon size={15} />
                </button>
              </div>
            )}

            {/* Hero Add Sources Button */}
            <button
              type="button"
              className={`btn-add-sources ${uploaderExpanded ? "active" : ""}`}
              onClick={() => setUploaderExpanded((prev) => !prev)}
            >
              <span aria-hidden="true">+</span>
              <span>{uploaderExpanded ? "Hide Uploader" : "Add Sources"}</span>
            </button>
          </div>
        </header>

        {/* Collapsible Cupertino Dropzone Drawer */}
        {uploaderExpanded && (
          <div className="sources-uploader-drawer">
            <div
              className={`drop-zone ${dragging ? "dragging" : ""}`}
              onDragOver={(e: DragEvent<HTMLDivElement>) => {
                e.preventDefault();
                setDragging(true);
              }}
              onDragLeave={() => setDragging(false)}
              onDrop={(e: DragEvent<HTMLDivElement>) => {
                e.preventDefault();
                setDragging(false);
                void addFiles(Array.from(e.dataTransfer.files ?? []));
              }}
            >
              <div className="drop-icon-wrap">
                <UploadCloudIcon size={32} />
              </div>
              <h3 className="drop-title">Upload or sync documents</h3>
              <p className="drop-subtitle">
                Drag and drop files here, or choose a file or folder to add to your sources.
              </p>

              <div className="format-pills-row">
                {["PDF", "Word", "Excel", "PowerPoint", "Markdown", "Text", "HTML"].map((ext) => (
                  <span key={ext} className="format-pill">
                    {ext}
                  </span>
                ))}
              </div>

              <div className="drop-btn-row">
                <button
                  type="button"
                  className="primary drop-btn"
                  disabled={uploadBusy}
                  onClick={() => fileInputRef.current?.click()}
                >
                  <UploadCloudIcon size={14} />
                  <span>{uploadBusy ? "Processing…" : "Browse files"}</span>
                </button>
                <button
                  type="button"
                  className="drop-btn folder-btn"
                  disabled={uploadBusy}
                  onClick={() => folderInputRef.current?.click()}
                >
                  <FolderIcon size={14} />
                  <span>Add Folder</span>
                </button>
              </div>
            </div>

            <input
              ref={fileInputRef}
              type="file"
              accept={ACCEPT}
              multiple
              hidden
              onChange={(e: ChangeEvent<HTMLInputElement>) => {
                void addFiles(Array.from(e.target.files ?? []));
              }}
            />
            <input
              ref={folderInputRef}
              type="file"
              multiple
              hidden
              onChange={(e: ChangeEvent<HTMLInputElement>) => {
                void addFiles(Array.from(e.target.files ?? []));
              }}
            />

            {/* Active Batch Upload Queue */}
            {uploadItems.length > 0 && (
              <div className="batch-upload-queue">
                <div className="queue-header-row">
                  <span className="queue-title">UPLOADING &bull; {uploadItems.length} FILES</span>
                  <button
                    type="button"
                    className="queue-clear-btn"
                    onClick={() =>
                      setUploadItems((prev) => prev.filter((i) => i.phase !== "ready" && i.phase !== "failed"))
                    }
                  >
                    Clear finished
                  </button>
                </div>
                <div className="queue-items-list">
                  {uploadItems.map((item) => (
                    <div key={item.key} className={`queue-item-card ${item.phase}`}>
                      <div className="queue-item-top">
                        <span className="queue-filename" title={item.filename}>
                          {item.filename}
                        </span>
                        <span className={`queue-phase-badge ${item.phase}`}>
                          {PHASE_LABEL[item.phase]}
                        </span>
                      </div>
                      {item.detail && <p className="queue-item-detail">{item.detail}</p>}
                      <div className="queue-progress-bar">
                        <div
                          className="queue-progress-fill"
                          style={{
                            width:
                              item.phase === "ready"
                                ? "100%"
                                : item.phase === "understanding"
                                  ? "75%"
                                  : item.phase === "reading"
                                    ? "35%"
                                    : item.phase === "failed"
                                      ? "100%"
                                      : "10%",
                          }}
                        />
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            )}
          </div>
        )}

        {/* ── Perspective 1: Library (Document Catalog) ── */}
        {perspective === "library" && (
          <div className="sources-content-body">
            {/* Filter Summary Row */}
            <div className="sources-filter-summary">
              <span className="filter-summary-count">
                Showing <strong>{filteredDocuments.length}</strong> of {documents.length} sources
                {totalPagesCount > 0 && ` &bull; ${totalPagesCount} pages`}
                {totalChunksCount > 0 && ` &bull; ${totalChunksCount} vector chunks`}
              </span>
              {(searchQuery || statusFilter !== "all" || formatFilter !== "all" || vendorFilter !== "all") && (
                <button
                  type="button"
                  className="filter-clear-summary-btn"
                  onClick={() => {
                    setSearchQuery("");
                    setStatusFilter("all");
                    setFormatFilter("all");
                    setVendorFilter("all");
                  }}
                >
                  Clear filters
                </button>
              )}
            </div>

            {loading ? (
              <div className="sources-loading-state">
                <div className="loading-pulse-ring" />
                <p>Retrieving documents from vector storage…</p>
              </div>
            ) : filteredDocuments.length === 0 ? (
              <div className="sources-empty-desk">
                <SparkleSquircleIcon size={52} className="empty-squircle" />
                <h3 className="empty-title">
                  {documents.length === 0 ? "Knowledge Catalog Empty" : "No documents match filters"}
                </h3>
                <p className="empty-desc">
                  {documents.length === 0
                    ? "Upload PDF technical guides, hardware specifications, datasheets, or markdown notes to ground the intelligence engine."
                    : "Try broadening your query or resetting status/vendor filters."}
                </p>
                <button
                  type="button"
                  className="primary drop-btn empty-action-btn"
                  onClick={() => {
                    setUploaderExpanded(true);
                    fileInputRef.current?.click();
                  }}
                >
                  <UploadCloudIcon size={14} />
                  <span>Upload Documents</span>
                </button>
              </div>
            ) : viewMode === "grid" ? (
              /* Grid View of Cupertino Document Cards */
              <div className="source-cards-grid">
                {filteredDocuments.map((doc, idx) => {
                  const isSelected = doc.id === selectedId;
                  const format = getFileFormatMeta(doc.original_filename);

                  return (
                    <article
                      key={doc.id}
                      className={`source-card ${isSelected ? "selected" : ""}`}
                      style={{ "--card-idx": Math.min(idx, 12) } as React.CSSProperties}
                      onClick={() => onSelect(doc.id)}
                      onKeyDown={(e) => {
                        if (e.key === "Enter" || e.key === " ") {
                          e.preventDefault();
                          onSelect(doc.id);
                        }
                      }}
                      tabIndex={0}
                      role="button"
                    >
                      {/* Card Top: Format Badge & Status */}
                      <div className="source-card-top">
                        <div
                          className="source-format-squircle"
                          style={{ background: format.bg, color: format.color }}
                        >
                          <FileTextIcon size={16} />
                          <span className="source-format-label">{format.label}</span>
                        </div>

                        <span className={`source-status-badge ${doc.status}`}>
                          {doc.status === "ready" && <span className="status-dot-mini ready" />}
                          {doc.status === "processing" && <span className="status-dot-mini processing" />}
                          {doc.status}
                        </span>
                      </div>

                      {/* Card Body: Title & Summary Preview */}
                      <div className="source-card-body">
                        <h3 className="source-card-title" title={doc.original_filename}>
                          {doc.title || doc.original_filename}
                        </h3>
                        {doc.vendor && <span className="source-vendor-chip">{doc.vendor}</span>}
                        {doc.summary ? (
                          <p className="source-card-snippet">{doc.summary}</p>
                        ) : (
                          <p className="source-card-snippet muted">
                            {doc.status === "ready" ? "Indexed and ready for grounded questions." : "Processing file…"}
                          </p>
                        )}
                      </div>

                      {/* Card Meta Stats: Size, Pages, Chunks */}
                      <div className="source-card-meta">
                        <span>{formatSize(doc.file_size)}</span>
                        {doc.page_count ? <span>&bull; {doc.page_count} pp</span> : null}
                        {doc.chunk_count ? <span>&bull; {doc.chunk_count} chunks</span> : null}
                        {doc.ocr_applied ? <span className="source-ocr-pill">OCR</span> : null}
                      </div>

                      {/* Hover / Direct Action Bar */}
                      <div className="source-card-actions" onClick={(e) => e.stopPropagation()}>
                        <button
                          type="button"
                          className="source-act-btn inspect-btn"
                          onClick={() => onSelect(doc.id)}
                          title="Inspect document synthesis and passages"
                        >
                          Inspect
                        </button>
                        <button
                          type="button"
                          className="source-act-btn ask-btn"
                          onClick={() => {
                            const title = doc.title || doc.original_filename;
                            onNavigate("ask", `Summarize key capabilities, architecture, and requirements in ${title}`);
                          }}
                          title="Ask Intelligence about this source"
                        >
                          <StarIcon size={12} />
                          <span>Ask AI</span>
                        </button>
                        {doc.status === "failed" && (
                          <button
                            type="button"
                            className="source-act-btn retry-btn"
                            onClick={() => void reprocessDocument(doc.id)}
                            title="Retry ingestion"
                          >
                            <RefreshCwIcon size={12} />
                          </button>
                        )}
                        <button
                          type="button"
                          className={`source-act-btn delete-btn ${pendingDeleteId === doc.id ? "confirming" : ""}`}
                          onClick={() => {
                            if (pendingDeleteId !== doc.id) {
                              setPendingDeleteId(doc.id);
                              return;
                            }
                            setPendingDeleteId(null);
                            void removeDocument(doc.id);
                          }}
                          onBlur={() => setPendingDeleteId((cur) => (cur === doc.id ? null : cur))}
                          title={pendingDeleteId === doc.id ? "Click again to confirm delete" : "Delete source"}
                        >
                          {pendingDeleteId === doc.id ? <CheckIcon size={12} /> : <TrashIcon size={12} />}
                          <span>{pendingDeleteId === doc.id ? "Confirm" : ""}</span>
                        </button>
                      </div>
                    </article>
                  );
                })}
              </div>
            ) : (
              /* Compact List View of Cupertino Table */
              <div className="source-list-table">
                <div className="table-header-row">
                  <span className="col-name">SOURCE</span>
                  <span className="col-vendor">VENDOR</span>
                  <span className="col-size">SIZE</span>
                  <span className="col-chunks">PASSAGES</span>
                  <span className="col-status">STATUS</span>
                  <span className="col-actions">ACTIONS</span>
                </div>
                {filteredDocuments.map((doc, idx) => {
                  const isSelected = doc.id === selectedId;
                  const format = getFileFormatMeta(doc.original_filename);

                  return (
                    <div
                      key={doc.id}
                      className={`table-row ${isSelected ? "selected" : ""}`}
                      style={{ "--card-idx": Math.min(idx, 12) } as React.CSSProperties}
                      onClick={() => onSelect(doc.id)}
                    >
                      <div className="col-name cell-name">
                        <span
                          className="table-format-badge"
                          style={{ background: format.bg, color: format.color }}
                        >
                          {format.label}
                        </span>
                        <span className="doc-title-text" title={doc.original_filename}>
                          {doc.title || doc.original_filename}
                        </span>
                      </div>
                      <div className="col-vendor cell-text">
                        {doc.vendor || <span className="muted">&mdash;</span>}
                      </div>
                      <div className="col-size cell-text">{formatSize(doc.file_size)}</div>
                      <div className="col-chunks cell-text">
                        {doc.chunk_count} {doc.page_count ? `(${doc.page_count} pp)` : ""}
                      </div>
                      <div className="col-status cell-badge">
                        <span className={`source-status-badge ${doc.status}`}>{doc.status}</span>
                      </div>
                      <div className="col-actions cell-actions" onClick={(e) => e.stopPropagation()}>
                        <button
                          type="button"
                          className="table-act-btn ask-pill"
                          onClick={() => {
                            const title = doc.title || doc.original_filename;
                            onNavigate("ask", `Summarize key capabilities in ${title}`);
                          }}
                        >
                          <StarIcon size={11} />
                          <span>Ask AI</span>
                        </button>
                        <button
                          type="button"
                          className="table-act-btn delete-pill"
                          onClick={() => void removeDocument(doc.id)}
                        >
                          <TrashIcon size={11} />
                        </button>
                      </div>
                    </div>
                  );
                })}
              </div>
            )}
          </div>
        )}

        {/* ── Perspective 2: Passages (Hybrid Vector Search) ── */}
        {perspective === "passages" && (
          <div className="sources-content-body passages-view">
            <div className="passages-hero-box">
              <h2 className="passages-hero-title">Deep Passage Hybrid Search</h2>
              <p className="passages-hero-sub">
                Dual-engine retrieval (HNSW Vector + BM25 Keyword) fused with Reciprocal Rank Fusion (RRF).
              </p>
            </div>

            <form onSubmit={handlePassageSearch} className="passages-search-form">
              <div className="passages-input-wrap">
                <SearchIcon size={16} className="passages-search-icon" />
                <input
                  type="text"
                  className="passages-search-input"
                  placeholder="Ask about SLA clauses, SKU conflicts, latency specifications, upgrade paths…"
                  value={passageQuery}
                  onChange={(e) => setPassageQuery(e.target.value)}
                />
                <button
                  type="submit"
                  className="primary passages-search-submit"
                  disabled={passageLoading || !passageQuery.trim()}
                >
                  {passageLoading ? "Searching…" : "Search Index"}
                </button>
              </div>

              <div className="passages-filter-options">
                <label className="checkbox-option">
                  <input
                    type="checkbox"
                    checked={passageApprovedOnly}
                    onChange={(e) => setPassageApprovedOnly(e.target.checked)}
                  />
                  <span>Ready sources only (Approved)</span>
                </label>
                <label className="checkbox-option">
                  <input
                    type="checkbox"
                    checked={passageExcludeInjection}
                    onChange={(e) => setPassageExcludeInjection(e.target.checked)}
                  />
                  <span>Exclude instruction injection flags</span>
                </label>
              </div>
            </form>

            {passageResult && (
              <div className="passages-results-container">
                <div className="passages-telemetry-bar">
                  <span className="telemetry-count">
                    {passageResult.candidate_count} candidates &bull; top {passageResult.hits.length} shown
                  </span>
                  <div className="timing-badges">
                    <span className="timing-tag">Total: {passageResult.timings_ms.total_ms}ms</span>
                    {passageResult.timings_ms.vector_ms !== undefined && (
                      <span className="timing-tag">HNSW: {passageResult.timings_ms.vector_ms}ms</span>
                    )}
                    {passageResult.timings_ms.keyword_ms !== undefined && (
                      <span className="timing-tag">BM25: {passageResult.timings_ms.keyword_ms}ms</span>
                    )}
                    <span className="timing-tag">RRF Fuse: {passageResult.timings_ms.fuse_ms}ms</span>
                  </div>
                </div>

                <div className="passage-hits-list">
                  {passageResult.hits.map((hit: SearchHit, idx: number) => {
                    const isExpanded = expandedChunkId === hit.chunk_id;

                    return (
                      <article
                        key={hit.chunk_id}
                        className={`hit-card ${isExpanded ? "expanded" : ""}`}
                        onClick={() => {
                          setExpandedChunkId(isExpanded ? null : hit.chunk_id);
                          if (hit.document_id) {
                            onSelect(hit.document_id);
                            setInspectorTab("passages");
                          }
                        }}
                      >
                        <div className="hit-header">
                          <div className="hit-title">
                            <span className="rank-num">#{String(idx + 1).padStart(2, "0")}</span>
                            <strong>{hit.document_title || hit.original_filename}</strong>
                            {hit.citation && <span className="citation-badge">{hit.citation}</span>}
                          </div>
                          <div className="hit-scores">
                            <span className="score-pill">RRF {hit.rrf_score.toFixed(4)}</span>
                            {hit.ranks?.vector !== undefined && (
                              <span className="rank-pill">Vec #{hit.ranks.vector}</span>
                            )}
                            {hit.ranks?.keyword !== undefined && (
                              <span className="rank-pill">Key #{hit.ranks.keyword}</span>
                            )}
                          </div>
                        </div>

                        <div className="hit-provenance">
                          {hit.vendor && <span className="prov-tag">Vendor {hit.vendor}</span>}
                          {hit.approval_state && (
                            <span className={`prov-tag ${hit.approval_state}`}>{hit.approval_state}</span>
                          )}
                          <span className={`prov-tag ${hit.is_stale ? "stale" : "fresh"}`}>
                            {hit.is_stale ? "Stale" : "Fresh"}
                          </span>
                          {hit.page_number && <span className="prov-tag">Page {hit.page_number}</span>}
                        </div>

                        <p className={`hit-snippet ${isExpanded ? "full" : ""}`}>{hit.text}</p>
                        <div className="expand-hint">
                          {isExpanded ? "Collapse passage" : "Expand passage & inspect in sidebar"}
                        </div>
                      </article>
                    );
                  })}
                </div>
              </div>
            )}
          </div>
        )}

        {/* ── Perspective 3: Watches (Datasheet Crawler & Staleness) ── */}
        {perspective === "watches" && (
          <div className="sources-content-body watches-view">
            {watchMessage && <div className="banner info">{watchMessage}</div>}

            <div className="watches-hero-box">
              <h2 className="watches-hero-title">Live Datasheet &amp; URL Watches</h2>
              <p className="watches-hero-sub">
                Register public datasheets or vendor portals. The crawler periodically hashes upstream documents and flags staleness.
              </p>
            </div>

            <form onSubmit={handleAddWatch} className="watches-form-card">
              <h3 className="watches-form-title">Watch an Upstream URL</h3>
              <div className="watches-inputs-row">
                <input
                  type="text"
                  className="chat-input"
                  placeholder="Label: Huawei Cloud Sizing Datasheet"
                  value={watchLabel}
                  onChange={(e) => setWatchLabel(e.target.value)}
                  disabled={watchBusy}
                />
                <input
                  type="url"
                  className="chat-input"
                  placeholder="https://vendor.com/datasheet.pdf"
                  value={watchUrl}
                  onChange={(e) => setWatchUrl(e.target.value)}
                  disabled={watchBusy}
                />
                <button
                  type="submit"
                  className="primary watch-submit-btn"
                  disabled={watchBusy || !watchLabel.trim() || !watchUrl.trim()}
                >
                  {watchBusy ? "Adding…" : "Watch URL"}
                </button>
              </div>
            </form>

            <div className="watches-sections-grid">
              {/* Monitored Sources */}
              <div className="watches-column">
                <h3 className="watches-col-title">MONITORED SOURCES ({watchSources.length})</h3>
                {watchSources.length === 0 ? (
                  <p className="empty-copy">Nothing on the watch list yet. Add a public datasheet URL above.</p>
                ) : (
                  <ul className="watches-list">
                    {watchSources.map((row) => (
                      <li key={row.id} className="watch-item-card">
                        <div className="watch-item-info">
                          <div className="watch-item-header">
                            <strong>{row.label}</strong>
                            <span className={`stamp ${row.status === "stale" ? "stale" : "fresh"}`}>
                              {row.status}
                            </span>
                          </div>
                          <p className="watch-item-url">{row.url}</p>
                        </div>
                        <button
                          type="button"
                          className="watch-check-btn"
                          disabled={watchBusy}
                          onClick={() => void handleCheckWatch(row.id)}
                        >
                          Check now
                        </button>
                      </li>
                    ))}
                  </ul>
                )}
              </div>

              {/* Staleness Alerts */}
              <div className="watches-column">
                <h3 className="watches-col-title">STALENESS ALERTS ({watchAlerts.length})</h3>
                {watchAlerts.length === 0 ? (
                  <p className="empty-copy">No open staleness alerts. All upstream hashes match the indexed versions.</p>
                ) : (
                  <ul className="watches-list">
                    {watchAlerts.map((alert) => (
                      <li key={alert.id} className="alert-item-card">
                        <div className="alert-item-info">
                          <span className="stamp stale">{alert.kind}</span>
                          {alert.pages && alert.pages.length > 0 ? (
                            alert.pages.map((p) => (
                              <p key={`${alert.id}-${p.url}`} className="alert-page-text">
                                {p.change}: {p.url}
                              </p>
                            ))
                          ) : (
                            <p className="alert-page-text">
                              Hash: {alert.previous_hash?.slice(0, 10)} &rarr; {alert.new_hash?.slice(0, 10)}
                            </p>
                          )}
                        </div>
                        <button
                          type="button"
                          className="alert-ack-btn"
                          onClick={() => void handleAckAlert(alert.id)}
                        >
                          Acknowledge
                        </button>
                      </li>
                    ))}
                  </ul>
                )}
              </div>
            </div>
          </div>
        )}
      </main>

      {/* ── Right Column: Live Source & Passage Inspector ────────────── */}
      <aside className="sources-side">
        <div className="side-section-header">
          <span className="side-title">SOURCE DETAILS</span>
          <span className="side-meta-mono">Live Inspector</span>
        </div>

        {selectedDoc ? (
          <div className="inspector-content">
            {/* Selected Document Hero Card */}
            <div className="inspector-hero-card">
              <div className="inspector-hero-top">
                <div
                  className="inspector-format-badge"
                  style={{
                    background: getFileFormatMeta(selectedDoc.original_filename).bg,
                    color: getFileFormatMeta(selectedDoc.original_filename).color,
                  }}
                >
                  <FileTextIcon size={18} />
                </div>
                <div className="inspector-hero-titles">
                  <h3 className="inspector-title" title={selectedDoc.original_filename}>
                    {selectedDoc.title || selectedDoc.original_filename}
                  </h3>
                  <span className="inspector-vendor">{selectedDoc.vendor || "Catalog Source"}</span>
                </div>
              </div>

              {/* Instant "Ask Intelligence" Hero Action */}
              <button
                type="button"
                className="btn-ask-intelligence-hero"
                onClick={() => {
                  const title = selectedDoc.title || selectedDoc.original_filename;
                  onNavigate(
                    "ask",
                    `Summarize key specifications, architecture, and requirements in ${title}`
                  );
                }}
              >
                <StarIcon size={14} />
                <span>Ask Intelligence about this source</span>
                <ExternalLinkIcon size={13} style={{ marginLeft: "auto", opacity: 0.7 }} />
              </button>
            </div>

            {/* Inspector Sub-Tabs Segmented Control */}
            <div className="inspector-subtabs">
              <button
                type="button"
                className={`subtab-btn ${inspectorTab === "insights" ? "active" : ""}`}
                onClick={() => setInspectorTab("insights")}
              >
                Insights
              </button>
              <button
                type="button"
                className={`subtab-btn ${inspectorTab === "passages" ? "active" : ""}`}
                onClick={() => setInspectorTab("passages")}
              >
                Passages ({docChunks.length})
              </button>
              <button
                type="button"
                className={`subtab-btn ${inspectorTab === "studio" ? "active" : ""}`}
                onClick={() => setInspectorTab("studio")}
              >
                AI Studio
              </button>
            </div>

            {/* Sub-Tab 1: Insights ("What I Learned") */}
            {inspectorTab === "insights" && (
              <div className="inspector-pane">
                <div className="pane-header-row">
                  <span className="pane-kicker">WHAT I LEARNED</span>
                  {!editing ? (
                    <button
                      type="button"
                      className="pane-link-action"
                      onClick={() => setEditing(true)}
                    >
                      Edit metadata
                    </button>
                  ) : null}
                </div>

                {editing ? (
                  <div className="inspector-edit-box">
                    <label>
                      <span>Executive Summary</span>
                      <textarea
                        value={summaryDraft}
                        onChange={(e) => setSummaryDraft(e.target.value)}
                        placeholder="Write a plain-language summary of what this document covers…"
                      />
                    </label>
                    <label>
                      <span>Brand / Vendor</span>
                      <input
                        value={vendorDraft}
                        onChange={(e) => setVendorDraft(e.target.value)}
                        placeholder="e.g. Huawei Cloud, Cisco, Jabra"
                      />
                    </label>
                    <label>
                      <span>Products Covered (comma separated)</span>
                      <input
                        value={productsDraft}
                        onChange={(e) => setProductsDraft(e.target.value)}
                        placeholder="e.g. Speak2 75, PanaCast 50"
                      />
                    </label>
                    <label>
                      <span>Valid Until Date</span>
                      <input
                        type="date"
                        value={validUntilDraft}
                        onChange={(e) => setValidUntilDraft(e.target.value)}
                      />
                    </label>
                    <div className="edit-actions-row">
                      <button
                        type="button"
                        className="primary edit-save-btn"
                        disabled={savingEdit}
                        onClick={() => void handleSaveEdit()}
                      >
                        {savingEdit ? "Saving…" : "Save Changes"}
                      </button>
                      <button
                        type="button"
                        className="edit-cancel-btn"
                        disabled={savingEdit}
                        onClick={() => setEditing(false)}
                      >
                        Cancel
                      </button>
                    </div>
                  </div>
                ) : (
                  <>
                    <p className="inspector-summary-text">
                      {selectedDoc.summary ||
                        "No AI summary generated yet. You can click 'Edit metadata' to write one or ask questions."}
                    </p>

                    {/* Detected Products Chips */}
                    {(selectedDoc.detected_products?.length || selectedDoc.products_referenced?.length) ? (
                      <div className="inspector-block">
                        <span className="block-label">PRODUCTS MENTIONED</span>
                        <div className="chips-wrap">
                          {(selectedDoc.detected_products || selectedDoc.products_referenced || []).map(
                            (prod) => (
                              <button
                                key={prod}
                                type="button"
                                className="apple-product-chip"
                                onClick={() => setSearchQuery(prod)}
                                title={`Filter library by ${prod}`}
                              >
                                {prod}
                              </button>
                            )
                          )}
                        </div>
                      </div>
                    ) : null}

                    {/* Key Facts Worth Remembering */}
                    {selectedDoc.key_facts && selectedDoc.key_facts.length > 0 && (
                      <div className="inspector-block">
                        <span className="block-label">WORTH REMEMBERING</span>
                        <ul className="facts-list">
                          {selectedDoc.key_facts.map((fact, index) => (
                            <li key={`${fact.label}-${index}`} className="fact-item">
                              <span className="fact-item-label">{fact.label}</span>
                              <span className="fact-item-val">{fact.value}</span>
                            </li>
                          ))}
                        </ul>
                      </div>
                    )}

                    {/* Topic Tags */}
                    {selectedDoc.topic_tags && selectedDoc.topic_tags.length > 0 && (
                      <div className="inspector-block">
                        <span className="block-label">TOPICS</span>
                        <div className="chips-wrap">
                          {selectedDoc.topic_tags.map((tag) => (
                            <span key={tag} className="apple-topic-chip">
                              {tag}
                            </span>
                          ))}
                        </div>
                      </div>
                    )}

                    {/* Suggested Knowledge Map Edges */}
                    {suggestions.length > 0 && (
                      <div className="inspector-block">
                        <span className="block-label">SUGGESTED MAP EDGES</span>
                        <ul className="suggestions-list">
                          {suggestions.map((edge) => (
                            <li key={edge.id} className="suggestion-item">
                              <p className="suggestion-edge-desc">
                                <strong>{edge.source_product_name}</strong>{" "}
                                {RELATION_WORDS[edge.relation_type] || edge.relation_type.replace(/_/g, " ")}{" "}
                                <strong>{edge.target_product_name}</strong>
                              </p>
                              <div className="suggestion-btn-row">
                                <button
                                  type="button"
                                  className="suggestion-accept-btn"
                                  onClick={() => void acceptEdge(edge.id)}
                                >
                                  Add to map
                                </button>
                                <button
                                  type="button"
                                  className="suggestion-dismiss-btn"
                                  onClick={() => void dismissEdge(edge.id)}
                                >
                                  Dismiss
                                </button>
                              </div>
                            </li>
                          ))}
                        </ul>
                      </div>
                    )}
                  </>
                )}
              </div>
            )}

            {/* Sub-Tab 2: Passages (Chunk Inspector) */}
            {inspectorTab === "passages" && (
              <div className="inspector-pane">
                <span className="pane-kicker">PASSAGES ({docChunks.length})</span>
                {chunksLoading ? (
                  <p className="muted">Retrieving vector passages…</p>
                ) : docChunks.length === 0 ? (
                  <p className="muted">No passages found. Ingestion may still be processing.</p>
                ) : (
                  <div className="inspector-chunks-list">
                    {docChunks.map((chunk) => (
                      <article key={chunk.id} className="inspector-chunk-card">
                        <div className="chunk-card-header">
                          <span className="chunk-num-badge">
                            #{String(chunk.chunk_index).padStart(2, "0")}
                          </span>
                          {chunk.page_number && (
                            <span className="chunk-meta-tag">p. {chunk.page_number}</span>
                          )}
                          {chunk.section_title && (
                            <span className="chunk-meta-tag" title={chunk.section_title}>
                              {chunk.section_title}
                            </span>
                          )}
                          <span className={`chunk-embedding-pill ${chunk.has_embedding ? "ok" : "warn"}`}>
                            {chunk.has_embedding ? "Embedded" : "Pending"}
                          </span>
                        </div>
                        <p className="chunk-card-text">{chunk.text}</p>
                      </article>
                    ))}
                  </div>
                )}
              </div>
            )}

            {/* Sub-Tab 3: AI Studio */}
            {inspectorTab === "studio" && (
              <div className="inspector-pane">
                <span className="pane-kicker">AI STUDIO SYNTHESIZER</span>
                <p className="studio-intro">
                  Trigger automated briefings, FAQs, or generate grounded questions from this document.
                </p>

                <div className="studio-action-buttons">
                  <button
                    type="button"
                    className="studio-btn"
                    disabled={studioBusy}
                    onClick={() => void runStudioQuestions()}
                  >
                    Suggested Questions
                  </button>
                  <button
                    type="button"
                    className="studio-btn"
                    disabled={studioBusy}
                    onClick={() => void runStudioAction("briefing")}
                  >
                    Executive Briefing
                  </button>
                  <button
                    type="button"
                    className="studio-btn"
                    disabled={studioBusy}
                    onClick={() => void runStudioAction("faq")}
                  >
                    Generate FAQ
                  </button>
                </div>

                {suggestedQuestions.length > 0 && (
                  <div className="studio-questions-box">
                    <span className="block-label">SUGGESTED QUESTIONS</span>
                    <div className="suggested-q-list">
                      {suggestedQuestions.map((q) => (
                        <button
                          key={q}
                          type="button"
                          className="suggested-q-btn"
                          onClick={() => onNavigate("ask", q)}
                        >
                          <span>{q}</span>
                          <ExternalLinkIcon size={12} />
                        </button>
                      ))}
                    </div>
                  </div>
                )}

                {studioResult && (
                  <div className="studio-result-markdown">
                    <AssistantMarkdown
                      text={studioResult.markdown}
                      citations={[]}
                      onSelect={() => undefined}
                    />
                  </div>
                )}
              </div>
            )}
          </div>
        ) : (
          /* Empty Inspector State (Matching Ask Intelligence) */
          <div className="citation-inspector-empty">
            <div className="citation-icon-squircle">
              <FileTextIcon size={24} />
            </div>
            <p className="citation-empty-text">No source selected</p>
            <p className="empty-inspector-sub">
              Select any document in the catalog to inspect its executive synthesis, detected products, graph relationships, and vector passages.
            </p>
            {documents.length > 0 && (
              <button
                type="button"
                className="citation-click-link"
                onClick={() => onSelect(documents[0].id)}
              >
                Inspect first document &rarr;
              </button>
            )}
          </div>
        )}
      </aside>
    </div>
  );
}
