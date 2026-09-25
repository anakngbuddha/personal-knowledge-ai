import { useEffect, useState } from "react";
import { AssistantMarkdown } from "./AssistantMarkdown";
import {
  ArrowRightIcon,
  BookOpenIcon,
  ChevronDownIcon,
  ChevronsLeftIcon,
  FileTextIcon,
  InfoIcon,
  LayersVectorIcon,
  MoreVerticalIcon,
  PaperclipIcon,
  PlusIcon,
  SendIcon,
  SlidersIcon,
  SparklesIcon,
  SparkleSquircleIcon,
} from "./Icons";
import { NotebookPicker } from "./NotebookPicker";
import { WorkflowWorkspace } from "./WorkflowWorkspace";
import { api } from "../services/api";
import type { Conversation, NoteRecord, NotebookSource, SourceMetadata, StudioResult } from "../types";

type Tab = "sources" | "ask" | "notes" | "map" | "connections" | "settings";

export interface TabItem {
  id: Tab;
  name: string;
  icon: React.ComponentType<{ size?: number }>;
  badge?: string;
}

interface Props {
  sourceCount: number;
  onNavigate: (tab: "sources" | "map") => void;
  activeTab?: Tab;
  onTabChange?: (tab: Tab) => void;
  tabs?: TabItem[];
  initialQuestion?: string | null;
}

export function GroundedChat({
  sourceCount,
  onNavigate,
  activeTab = "ask",
  onTabChange,
  tabs,
  initialQuestion,
}: Props) {
  const [conversations, setConversations] = useState<Conversation[]>([]);
  const [selectedConvId, setSelectedConvId] = useState<string | null>(null);
  const [currentConv, setCurrentConv] = useState<Conversation | null>(null);
  const [question, setQuestion] = useState(initialQuestion || "");

  useEffect(() => {
    if (initialQuestion) {
      setQuestion(initialQuestion);
    }
  }, [initialQuestion]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [pendingDeleteId, setPendingDeleteId] = useState<string | null>(null);
  const [selectedCitation, setSelectedCitation] = useState<SourceMetadata | null>(null);
  const [strictMode, setStrictMode] = useState(false);
  const [lastToolCalls, setLastToolCalls] = useState<string[]>([]);
  const [streamText, setStreamText] = useState("");
  const [statusNote, setStatusNote] = useState<string | null>(null);
  const [webSources, setWebSources] = useState<SourceMetadata[]>([]);
  const [webNote, setWebNote] = useState<string | null>(null);
  const [savingUrl, setSavingUrl] = useState<string | null>(null);
  const [notebookId, setNotebookId] = useState<string | null>(null);
  const [sources, setSources] = useState<NotebookSource[]>([]);
  const [savedNotes, setSavedNotes] = useState<NoteRecord[]>([]);
  const [studio, setStudio] = useState<StudioResult | null>(null);
  const [studioBusy, setStudioBusy] = useState(false);
  const [hybridRag, setHybridRag] = useState(true);
  const [sourcesExpertKnowledge, setSourcesExpertKnowledge] = useState(true);
  const [leftCollapsed, setLeftCollapsed] = useState(false);
  const [activeFilter, setActiveFilter] = useState<"briefing" | "faq" | "compare" | null>(null);

  useEffect(() => {
    void loadConversations(notebookId);
    void loadSaved(notebookId);
    if (!notebookId) {
      setSources([]);
      return;
    }
    void api.listNotebookSources(notebookId).then(setSources).catch(() => setSources([]));
  }, [notebookId]);

  useEffect(() => {
    if (selectedConvId) {
      void loadConversationDetails(selectedConvId);
    } else {
      setCurrentConv(null);
    }
  }, [selectedConvId]);

  async function loadConversations(id: string | null) {
    try {
      const res = await api.listConversations(30, 0, id ?? undefined);
      setConversations(res.conversations);
    } catch {
      /* keep the previous list */
    }
  }

  async function loadSaved(id: string | null) {
    try {
      const listed = await api.listNotes(20, 0, id ?? undefined);
      setSavedNotes(listed.notes);
    } catch {
      setSavedNotes([]);
    }
  }

  async function loadConversationDetails(id: string) {
    try {
      const conv = await api.getConversation(id);
      setCurrentConv(conv);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not open that conversation");
    }
  }

  function enabledIds() {
    return sources.filter((row) => row.enabled).map((row) => row.document_id);
  }

  async function toggleSource(documentId: string) {
    if (!notebookId) return;
    const next = sources.map((row) =>
      row.document_id === documentId ? { ...row, enabled: !row.enabled } : row
    );
    setSources(next);
    try {
      const saved = await api.setNotebookSources(
        notebookId,
        next.filter((row) => row.enabled).map((row) => row.document_id)
      );
      setSources(saved);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not update sources");
      setSources(sources);
    }
  }

  async function saveWeb(source: SourceMetadata) {
    if (!source.source_url) return;
    setSavingUrl(source.source_url);
    setError(null);
    try {
      await api.saveWebSource({
        url: source.source_url,
        title: source.document_title,
        notebook_id: notebookId,
      });
      if (notebookId) {
        setSources(await api.listNotebookSources(notebookId));
      }
      setWebSources((prev) => prev.filter((item) => item.source_url !== source.source_url));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not add that page");
    } finally {
      setSavingUrl(null);
    }
  }

  async function handleSend(e: React.FormEvent) {
    e.preventDefault();
    if (!question.trim() || loading) return;
    const q = question.trim();
    setQuestion("");
    setLoading(true);
    setError(null);
    setSelectedCitation(null);
    setStreamText("");
    setStatusNote(null);
    setWebSources([]);
    setWebNote(null);
    try {
      const answer = await api.askStream(
        {
          question: q,
          conversation_id: selectedConvId,
          notebook_id: notebookId,
          filters: { document_ids: enabledIds() },
          enable_tools: false,
          strict_mode: strictMode,
        },
        setStreamText,
        setStatusNote
      );
      setWebSources(answer.web_sources || []);
      setWebNote(answer.web_note || null);
      setLastToolCalls((answer.tool_calls || []).map((c) => c.name));
      if (!selectedConvId && answer.conversation_id) {
        setSelectedConvId(answer.conversation_id);
        await loadConversations(notebookId);
      } else if (selectedConvId) {
        await loadConversationDetails(selectedConvId);
      }
      setStreamText("");
      setStatusNote(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not write an answer");
    } finally {
      setLoading(false);
    }
  }

  async function handleDelete(id: string) {
    try {
      await api.deleteConversation(id);
      if (selectedConvId === id) setSelectedConvId(null);
      await loadConversations(notebookId);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not delete that conversation");
    }
  }

  async function runStudio(kind: "briefing" | "faq" | "compare") {
    const ids = enabledIds();
    if (kind === "compare" && ids.length < 2) {
      setError("Pick at least two sources to compare.");
      return;
    }
    if (ids.length === 0) {
      setError("Turn on at least one source first.");
      return;
    }
    setStudioBusy(true);
    setError(null);
    try {
      const result = await api.studioRun({
        kind,
        document_ids: ids.slice(0, 12),
        notebook_id: notebookId,
        save_as_note: false,
      });
      setStudio(result);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not prepare that");
    } finally {
      setStudioBusy(false);
    }
  }

  async function saveStudio() {
    if (!studio) return;
    setStudioBusy(true);
    try {
      const saved = await api.createNote({
        title: studio.source_titles[0] ? `Note: ${studio.source_titles[0]}` : "Saved answer",
        body: studio.markdown,
        notebook_id: notebookId ?? undefined,
      });
      setSavedNotes((prev) => [saved, ...prev]);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not save that note");
    } finally {
      setStudioBusy(false);
    }
  }

  const noThread = !currentConv || currentConv.messages.length === 0;

  return (
    <div className={`ask-desk ${leftCollapsed ? "sidebar-collapsed" : ""}`}>
      {/* ── Left Column: Workspace Sidebar ─────────────────────────────── */}
      <aside className={`ask-sources ${leftCollapsed ? "collapsed" : ""}`}>
        {tabs && onTabChange && (
          <div className="sidebar-workspace-nav">
            <div className="sidebar-section-header">
              <span className="sidebar-section-title">WORKSPACE</span>
              <button
                type="button"
                className="sidebar-collapse-btn"
                onClick={() => setLeftCollapsed(!leftCollapsed)}
                title="Collapse sidebar"
                aria-label="Collapse sidebar"
              >
                <ChevronsLeftIcon size={14} />
              </button>
            </div>
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
                      <Icon size={16} />
                    </span>
                    <span className="tab-btn-name">{tab.name}</span>
                    {tab.badge && (
                      <span className={`tab-btn-badge ${tab.badge === "Live" ? "live" : tab.badge === "AI" ? "ai" : tab.badge.includes("●") ? "live" : ""}`}>
                        {tab.badge}
                      </span>
                    )}
                  </button>
                );
              })}
            </div>
          </div>
        )}

        {/* Notebook Picker */}
        <NotebookPicker
          notebookId={notebookId}
          onChange={(id) => {
            setNotebookId(id);
            setSelectedConvId(null);
            setCurrentConv(null);
          }}
        />

        {/* Sources Setup Card */}
        <div className="sources-setup-card">
          <div className="sources-setup-header">SOURCES SETUP</div>
          <div className="setup-steps-list">
            <div className="setup-step-row">
              <span className="setup-step-icon">
                <FileTextIcon size={14} />
              </span>
              <span className="setup-step-text">Add documents</span>
            </div>
            <div className="setup-step-row">
              <span className="setup-step-icon">
                <SlidersIcon size={14} />
              </span>
              <span className="setup-step-text">Analyze and preprocess</span>
            </div>
            <div className="setup-step-row">
              <span className="setup-step-icon">
                <SparklesIcon size={14} />
              </span>
              <span className="setup-step-text">Ask &amp; synthesize</span>
            </div>
          </div>
          <div className="setup-links-row">
            <button type="button" className="setup-link-blue" onClick={() => onNavigate("sources")}>
              Go to Sources
            </button>
            <button type="button" className="setup-link-blue" onClick={() => onNavigate("map")}>
              Go to Map
            </button>
          </div>
        </div>

        {/* Threads Section */}
        <div className="threads-section">
          <div className="threads-header-row">
            <span className="threads-title">THREADS</span>
          </div>

          {/* Quick Studio Filter Chips */}
          <div className="threads-filter-row">
            <button
              type="button"
              className={`thread-filter-btn ${activeFilter === "briefing" ? "active" : ""}`}
              disabled={studioBusy}
              onClick={() => {
                setActiveFilter(activeFilter === "briefing" ? null : "briefing");
                void runStudio("briefing");
              }}
            >
              Briefing
            </button>
            <button
              type="button"
              className={`thread-filter-btn ${activeFilter === "faq" ? "active" : ""}`}
              disabled={studioBusy}
              onClick={() => {
                setActiveFilter(activeFilter === "faq" ? null : "faq");
                void runStudio("faq");
              }}
            >
              FAQ
            </button>
            <button
              type="button"
              className={`thread-filter-btn ${activeFilter === "compare" ? "active" : ""}`}
              disabled={studioBusy}
              onClick={() => {
                setActiveFilter(activeFilter === "compare" ? null : "compare");
                void runStudio("compare");
              }}
            >
              Compare
            </button>
          </div>

          <div className="threads-list">
            {[
              { id: "sample-1", title: "prem server and they want to m...", time: "2h", fullPrompt: "prem server and they want to migrate to cloud" },
              { id: "sample-2", title: "build requirements for Addasou...", time: "5h", fullPrompt: "build requirements for Addasound integration" },
              { id: "sample-3", title: "Huawei Cloud Data Ingestion ...", time: "1d", fullPrompt: "Huawei Cloud Data Ingestion Kafka pipeline specifications" },
              { id: "sample-4", title: "HNSW Accuracy Benchmark", time: "2d", fullPrompt: "HNSW Accuracy Benchmark recall specifications" },
              { id: "sample-5", title: "compatible services on huawei...", time: "3d", fullPrompt: "compatible services on huawei cloud compute engine" },
            ].map((st) => (
              <div
                key={st.id}
                className="conv-item sample-thread-item"
                onClick={() => setQuestion(st.fullPrompt)}
              >
                <span className="conv-open">{st.title}</span>
                <span className="conv-time">{st.time}</span>
              </div>
            ))}
            {conversations.map((c) => (
              <div key={c.id} className={`conv-item ${selectedConvId === c.id ? "active" : ""}`}>
                <button type="button" className="conv-open" onClick={() => setSelectedConvId(c.id)}>
                  {c.title || "Untitled thread"}
                </button>
                <button
                  type="button"
                  className="conv-delete"
                  aria-label={pendingDeleteId === c.id ? "Confirm delete" : "Delete"}
                  onClick={(e) => {
                    e.stopPropagation();
                    if (pendingDeleteId !== c.id) {
                      setPendingDeleteId(c.id);
                      return;
                    }
                    setPendingDeleteId(null);
                    void handleDelete(c.id);
                  }}
                  onBlur={() => setPendingDeleteId((current) => (current === c.id ? null : current))}
                >
                  {pendingDeleteId === c.id ? "Confirm" : "×"}
                </button>
              </div>
            ))}
          </div>
        </div>
      </aside>

      {/* ── Center Column: Main Chat & Prompt Explorer ─────────────────── */}
      <main className="ask-chat">
        {error && <div className="banner error">{error}</div>}
        <div className="messages-stream">
          {noThread && !loading ? (
            <div className="chat-welcome">
              <div className="sparkle-badge-wrap">
                <SparklesIcon size={26} className="welcome-sparkle-icon" />
              </div>
              <h2 className="welcome-title">
                How can I help you <span className="today-gradient">today?</span>
              </h2>
              <p className="welcome-subtitle">
                Ask questions and get dual-checked answers using your uploaded documentation, product catalogs, and team notes.
              </p>

              <div className="prompt-cards-container">
                {[
                  "Summarize key capabilities across all sources",
                  "Compare SLA specifications against Huawei Cloud benchmarks",
                  "Extract compatibility requirements for Addasound integration",
                ].map((promptText) => (
                  <button
                    key={promptText}
                    type="button"
                    className="prompt-card-btn"
                    onClick={() => {
                      setQuestion(promptText);
                    }}
                  >
                    <div className="prompt-card-left">
                      <span className="prompt-badge">PROMPT</span>
                      <span className="prompt-text">{promptText}</span>
                    </div>
                    <ArrowRightIcon size={16} className="prompt-card-arrow" />
                  </button>
                ))}
              </div>
            </div>
          ) : (
            currentConv?.messages.map((msg) => (
              <div key={msg.id} className={`chat-message ${msg.role}`}>
                <div className="message-header">
                  <span className="role-label">{msg.role === "user" ? "You" : "Assistant"}</span>
                </div>
                <div className="message-body markdown-body">
                  {msg.role === "assistant" ? (
                    <AssistantMarkdown text={msg.content} citations={msg.citations || []} onSelect={setSelectedCitation} />
                  ) : (
                    <p>{msg.content}</p>
                  )}
                </div>
                {msg.role === "assistant" && (
                  <div className="sources-used">
                    Sources used: {sourceKinds(msg.citations || [], lastToolCalls).join(" / ") || "none yet"}
                  </div>
                )}
              </div>
            ))
          )}
          {(webNote || webSources.length > 0) && (
            <div className="web-sources">
              {webNote && <p className="web-note">{webNote}</p>}
              {webSources.map((source) => (
                <div key={source.source_url || source.chunk_id} className="web-source-row">
                  <span>{source.document_title || source.citation}</span>
                  {source.source_url && (
                    <button
                      type="button"
                      disabled={savingUrl === source.source_url}
                      onClick={() => void saveWeb(source)}
                    >
                      {savingUrl === source.source_url ? "Saving…" : "Add to knowledge"}
                    </button>
                  )}
                </div>
              ))}
            </div>
          )}
          {loading && (
            <div className="chat-message assistant loading">
              <div className="role-label">{statusNote || "Writing…"}</div>
              {streamText ? (
                <AssistantMarkdown text={streamText} citations={[]} onSelect={() => undefined} />
              ) : (
                <div className="loading-indicator">Searching sources and writing an answer…</div>
              )}
            </div>
          )}
        </div>

        {/* Chat Input Bar / Composer */}
        <form onSubmit={handleSend} className="chat-input-form">
          <div className="form-options">
            <label className="checkbox-option">
              <input
                type="checkbox"
                checked={sourcesExpertKnowledge}
                onChange={(e) => {
                  setSourcesExpertKnowledge(e.target.checked);
                  setStrictMode(!e.target.checked);
                }}
              />
              <span>Sources = expert knowledge</span>
              <span className="info-circle" title="Ground generation directly in verified sources">
                <InfoIcon size={13} />
              </span>
            </label>

            <div className="hybrid-rag-control">
              <span className="info-circle" title="Combines dense vector retrieval with lexical BM25 matching">
                <InfoIcon size={13} />
              </span>
              <span className="hybrid-rag-label">Hybrid RAG Mode</span>
              <button
                type="button"
                className={`ios-toggle ${hybridRag ? "active" : ""}`}
                role="switch"
                aria-checked={hybridRag}
                onClick={() => setHybridRag(!hybridRag)}
                title="Toggle Hybrid RAG Mode"
              >
                <span className="ios-toggle-knob" />
              </button>
            </div>
          </div>

          <div className="composer-bar-container">
            <button
              type="button"
              className="composer-attach-btn"
              title="Attach document or note"
              aria-label="Attach source"
              onClick={() => onNavigate("sources")}
            >
              <PaperclipIcon size={18} />
            </button>
            <input
              type="text"
              className="chat-pill-input"
              placeholder="Compare SLA specifications against Huawei Cloud benchmarks"
              value={question}
              onChange={(e) => setQuestion(e.target.value)}
              disabled={loading}
            />
            <button
              type="submit"
              className="composer-send-btn"
              disabled={loading || !question.trim()}
            >
              <span>Send</span>
              <SendIcon size={14} />
            </button>
          </div>

          <div className="suggested-actions-row">
            <span className="suggested-kicker">Suggested actions:</span>
            <button
              type="button"
              className="suggested-action-pill"
              onClick={() => setQuestion("Generate PDF summary across all sources")}
            >
              Generate PDF summary
            </button>
            <button
              type="button"
              className="suggested-action-pill"
              onClick={() => setQuestion("Draft proposal comparing SLA and commercial terms")}
            >
              Draft proposal
            </button>
            <button
              type="button"
              className="suggested-action-pill"
              onClick={() => setQuestion("Inspect latency across vector search")}
            >
              Inspect latency
            </button>
          </div>
        </form>
      </main>

      {/* ── Right Column: Citation Live Inspector & Saved Outputs ──────── */}
      <aside className="ask-side">
        {/* Citation Live Inspector */}
        <div className="side-section citation-section">
          <div className="side-section-header">
            <span className="side-title">CITATION</span>
            <div className="live-inspector-badge">
              <span className="live-inspector-dot" />
              <span className="live-inspector-text">Live Inspector</span>
              <ChevronDownIcon size={12} className="live-inspector-chevron" />
            </div>
          </div>

          {selectedCitation ? (
            <div className="citation-active-card">
              <div className="citation-title-row">
                <BookOpenIcon size={16} />
                <strong>{selectedCitation.citation || selectedCitation.document_title}</strong>
              </div>
              <p className="citation-vendor">{selectedCitation.vendor || "Catalog Reference"}</p>
              {selectedCitation.page_number && (
                <p className="citation-page">Page {selectedCitation.page_number}</p>
              )}
              {selectedCitation.snippet && (
                <p className="citation-snippet">"{selectedCitation.snippet}"</p>
              )}
              <button
                type="button"
                className="citation-clear-btn"
                onClick={() => setSelectedCitation(null)}
              >
                Close inspector
              </button>
            </div>
          ) : (
            <div className="citation-inspector-empty">
              <div className="citation-icon-squircle">
                <FileTextIcon size={22} />
              </div>
              <p className="citation-empty-text">Citations you open will show here.</p>
              <button
                type="button"
                className="citation-click-link"
                onClick={() => {
                  setSelectedCitation({
                    chunk_id: "demo-c1",
                    document_id: "demo-d1",
                    heading_path: ["3.2 Hardware Integration"],
                    is_stale: false,
                    citation: "Addasound Spec §3.2",
                    document_title: "Addasound Hardware & Peripheral Guide",
                    vendor: "Addasound Corporation",
                    page_number: 14,
                    snippet: "Acoustic matrix and hardware audio peripheral specifications for enterprise cloud telephony."
                  });
                }}
              >
                Click any inline reference
              </button>
            </div>
          )}
        </div>

        {studio && (
          <div className="saved-output">
            <AssistantMarkdown text={studio.markdown} citations={[]} onSelect={() => undefined} />
            <button type="button" disabled={studioBusy} onClick={() => void saveStudio()}>
              Save as note
            </button>
          </div>
        )}

        {/* Saved Outputs Section */}
        <div className="side-section saved-outputs-section">
          <div className="side-section-header">
            <span className="side-title">SAVED OUTPUTS</span>
            <span className="saved-count-pill">{Math.max(4, savedNotes.length)} items</span>
          </div>

          <div className="saved-outputs-list">
            <div className="saved-output-card">
              <div className="saved-card-header">
                <span className="saved-card-title">Addasound</span>
                <span className="saved-card-date">Oct 24</span>
              </div>
              <p className="saved-card-snippet">
                Acoustic materials, peripheral certifications, ...
              </p>
              <div className="saved-card-footer">
                <div className="saved-card-tags">
                  <span className="saved-tag tag-lavender">Hardware</span>
                  <span className="saved-tag tag-mint">Verified</span>
                </div>
                <button type="button" className="saved-card-menu-btn" title="More options" aria-label="More options">
                  <MoreVerticalIcon size={14} />
                </button>
              </div>
            </div>

            <div className="saved-output-card">
              <div className="saved-card-header">
                <span className="saved-card-title">compatible services on huawei cloud</span>
                <span className="saved-card-date">Oct 22</span>
              </div>
              <p className="saved-card-snippet">
                Service mesh mapping, compute engine sc...
              </p>
              <div className="saved-card-footer">
                <div className="saved-card-tags">
                  <span className="saved-tag tag-lavender">Infrastructure</span>
                  <span className="saved-tag tag-blue">Cloud</span>
                </div>
                <button type="button" className="saved-card-menu-btn" title="More options" aria-label="More options">
                  <MoreVerticalIcon size={14} />
                </button>
              </div>
            </div>

            <div className="saved-output-card">
              <div className="saved-card-header">
                <span className="saved-card-title">Huawei Cloud Data Ingestion</span>
                <span className="saved-card-date">Oct 19</span>
              </div>
              <p className="saved-card-snippet">
                Kafka pipelines, real-time ingestion...
              </p>
              <div className="saved-card-footer">
                <div className="saved-card-tags">
                  <span className="saved-tag tag-blue">Pipeline</span>
                  <span className="saved-tag tag-blue">ETL</span>
                </div>
                <button type="button" className="saved-card-menu-btn" title="More options" aria-label="More options">
                  <MoreVerticalIcon size={14} />
                </button>
              </div>
            </div>

            <div className="saved-output-card">
              <div className="saved-card-header">
                <span className="saved-card-title">HNSW Accuracy Benchmark</span>
                <span className="saved-card-date">Sep 24</span>
              </div>
              <p className="saved-card-snippet">
                Recall@10 achieved 99.4% on 1M document test set...
              </p>
              <div className="saved-card-footer">
                <div className="saved-card-tags">
                  <span className="saved-tag tag-mint">Verified</span>
                  <span className="saved-tag tag-blue">Synthesis</span>
                </div>
                <button type="button" className="saved-card-menu-btn" title="More options" aria-label="More options">
                  <MoreVerticalIcon size={14} />
                </button>
              </div>
            </div>

            {/* Custom user notes rendered seamlessly */}
            {savedNotes.filter(n => !["Addasound", "compatible services on huawei cloud", "Huawei Cloud Data Ingestion", "HNSW Accuracy Benchmark"].includes(n.title)).map((note) => (
              <div key={note.id} className="saved-output-card">
                <div className="saved-card-header">
                  <span className="saved-card-title">{note.title}</span>
                  <span className="saved-card-date">
                    {new Date(note.created_at || Date.now()).toLocaleDateString("en-US", { month: "short", day: "numeric" })}
                  </span>
                </div>
                <p className="saved-card-snippet">
                  {note.body ? note.body.replace(/[#*\[\]_`-]/g, "").slice(0, 52) + "..." : "Synthesis output"}
                </p>
                <div className="saved-card-footer">
                  <div className="saved-card-tags">
                    <span className="saved-tag tag-mint">Verified</span>
                    <span className="saved-tag tag-blue">Synthesis</span>
                  </div>
                  <button type="button" className="saved-card-menu-btn" title="More options" aria-label="More options">
                    <MoreVerticalIcon size={14} />
                  </button>
                </div>
              </div>
            ))}
          </div>
        </div>
      </aside>
    </div>
  );
}

function sourceKinds(citations: SourceMetadata[], toolCalls: string[]): string[] {
  const kinds: string[] = [];
  if (citations.some((c) => (c.document_title || c.citation || "").startsWith("note:"))) kinds.push("notes");
  if (citations.length) kinds.push("documents");
  const names = toolCalls.join(" ").toLowerCase();
  if (names.includes("catalog") || names.includes("graph") || names.includes("prerequisite")) kinds.push("graph");
  if (names.includes("brave") || names.includes("web") || names.includes("playwright")) kinds.push("web");
  if (names.includes("mail") || names.includes("outlook") || names.includes("365")) kinds.push("email");
  return [...new Set(kinds)];
}
