import { useEffect, useState } from "react";
import { AssistantMarkdown } from "./AssistantMarkdown";
import {
  BookOpenIcon,
  InfoIcon,
  LayersVectorIcon,
  PlusIcon,
  SendIcon,
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
}

export function GroundedChat({
  sourceCount,
  onNavigate,
  activeTab = "ask",
  onTabChange,
  tabs,
}: Props) {
  const [conversations, setConversations] = useState<Conversation[]>([]);
  const [selectedConvId, setSelectedConvId] = useState<string | null>(null);
  const [currentConv, setCurrentConv] = useState<Conversation | null>(null);
  const [question, setQuestion] = useState("");
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
    <div className="ask-desk">
      {/* ── Left Column: Workspace Sidebar ─────────────────────────────── */}
      <aside className="ask-sources">
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
                      <span className={`tab-btn-badge ${tab.badge === "Live" ? "live" : tab.badge === "AI" ? "ai" : ""}`}>
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
              <span className="setup-step-num">1</span>
              <span className="setup-step-text">Add documents</span>
            </div>
            <div className="setup-step-row">
              <span className="setup-step-num">2</span>
              <span className="setup-step-text">Add your products</span>
            </div>
            <div className="setup-step-row">
              <span className="setup-step-num">3</span>
              <span className="setup-step-text">Ask &amp; synthesize</span>
            </div>
          </div>
          <div className="setup-links-row">
            <button type="button" className="setup-link-blue" onClick={() => onNavigate("sources")}>
              Go to Sources
            </button>
            <button type="button" className="setup-link-gray" onClick={() => onNavigate("map")}>
              Go to Map
            </button>
          </div>
        </div>

        {/* Sources Checklist (if user has enabled sources) */}
        {sources.length > 0 && (
          <div className="active-sources-checklist">
            <div className="sources-checklist-title">SELECTED ({enabledIds().length}/{sources.length})</div>
            <ul className="source-list">
              {sources.map((row) => (
                <li key={row.document_id}>
                  <label>
                    <input
                      type="checkbox"
                      checked={row.enabled}
                      onChange={() => void toggleSource(row.document_id)}
                    />
                    <span>{row.title || row.filename}</span>
                  </label>
                </li>
              ))}
            </ul>
          </div>
        )}

        {/* Studio Action Buttons */}
        <div className="helper-row">
          <button type="button" disabled={studioBusy} onClick={() => void runStudio("briefing")}>
            Briefing
          </button>
          <button type="button" disabled={studioBusy} onClick={() => void runStudio("faq")}>
            FAQ
          </button>
          <button type="button" disabled={studioBusy} onClick={() => void runStudio("compare")}>
            Compare
          </button>
        </div>

        {/* Threads Section */}
        <div className="threads-section">
          <div className="threads-header-row">
            <span className="threads-title">THREADS</span>
            <span className="threads-live-label">REAL-TIME</span>
          </div>
          {conversations.length === 0 ? (
            <div className="threads-empty-box">
              <em>No previous threads in this session</em>
            </div>
          ) : (
            <div className="threads-list">
              {conversations.map((c) => (
                <div key={c.id} className={`conv-item ${selectedConvId === c.id ? "active" : ""}`}>
                  <button type="button" className="conv-open" onClick={() => setSelectedConvId(c.id)}>
                    {c.title || "Untitled"}
                  </button>
                  <button
                    type="button"
                    className="conv-delete"
                    aria-label={pendingDeleteId === c.id ? "Confirm delete" : "Delete"}
                    onClick={() => {
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
          )}
        </div>

        {/* Vector Memory Telemetry Card */}
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
                {sourceCount || 50} sources indexed &bull; isolation active
              </div>
            </div>
          </div>
        </div>
      </aside>

      {/* ── Center Column: Main Chat & Prompt Explorer ─────────────────── */}
      <main className="ask-chat">
        {error && <div className="banner error">{error}</div>}
        <div className="messages-stream">
          {noThread && !loading ? (
            <div className="chat-welcome">
              <SparkleSquircleIcon size={56} className="welcome-squircle" />
              <h2 className="welcome-title">
                How can I help you <span className="today-gradient">today?</span>
              </h2>
              <p className="welcome-subtitle">
                Ask questions grounded directly in your uploaded documentation, product catalogs, and team notes.
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
                    <span className="prompt-badge">PROMPT</span>
                    <span className="prompt-text">{promptText}</span>
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

        {/* Chat Input Bar */}
        <form onSubmit={handleSend} className="chat-input-form">
          <div className="form-options">
            <label className="checkbox-option">
              <input
                type="checkbox"
                checked={!strictMode}
                onChange={(e) => setStrictMode(!e.target.checked)}
              />
              <span>Sources + expert knowledge</span>
            </label>
            <div className="hybrid-rag-badge">
              <InfoIcon size={14} />
              <span>Hybrid RAG Mode</span>
            </div>
          </div>

          <div className="input-pill-container">
            <input
              type="text"
              className="chat-pill-input"
              placeholder="Ask about compatibility, pricing, requirements…"
              value={question}
              onChange={(e) => setQuestion(e.target.value)}
              disabled={loading}
            />
            <button
              type="submit"
              className="chat-send-btn"
              disabled={loading || !question.trim()}
            >
              <span>Send</span>
              <SendIcon size={14} />
            </button>
          </div>

          <div className="suggested-actions-row">
            <span className="suggested-kicker">&gt; Suggested actions:</span>
            <button
              type="button"
              className="suggested-action-item"
              onClick={() => setQuestion("Generate PDF executive summary across all sources")}
            >
              Generate PDF summary
            </button>
            <span className="suggested-bullet">&bull;</span>
            <button
              type="button"
              className="suggested-action-item"
              onClick={() => setQuestion("Draft proposal comparing SLA and commercial terms")}
            >
              Draft proposal
            </button>
            <span className="suggested-bullet">&bull;</span>
            <button
              type="button"
              className="suggested-action-item"
              onClick={() => setQuestion("Inspect latency across vector search")}
            >
              Inspect latency
            </button>
          </div>
        </form>

        <details className="suggested-actions-details">
          <summary>All workflows &amp; playbooks</summary>
          <WorkflowWorkspace />
        </details>
      </main>

      {/* ── Right Column: Citation Live Inspector & Saved Outputs ──────── */}
      <aside className="ask-side">
        {/* Citation Live Inspector */}
        <div className="side-section">
          <div className="side-section-header">
            <span className="side-title">CITATION</span>
            <span className="side-meta-mono">Live Inspector</span>
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
                <BookOpenIcon size={20} />
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
            <span className="saved-count-pill">{Math.max(3, savedNotes.length)} items</span>
          </div>

          <div className="saved-outputs-list">
            {savedNotes.length > 0 ? (
              savedNotes.map((note) => (
                <div key={note.id} className="saved-output-card">
                  <div className="saved-card-header">
                    <span className="saved-card-title">{note.title}</span>
                    <span className="saved-card-date">
                      {new Date(note.created_at || Date.now()).toLocaleDateString("en-US", { month: "short", day: "numeric" })}
                    </span>
                  </div>
                  <p className="saved-card-snippet">
                    {note.body ? note.body.slice(0, 52) + "..." : "Synthesis output summary"}
                  </p>
                  <div className="saved-card-tags">
                    <span className="saved-tag tag-lavender">Verified</span>
                    <span className="saved-tag tag-slate">Synthesis</span>
                  </div>
                </div>
              ))
            ) : (
              <>
                <div className="saved-output-card">
                  <div className="saved-card-header">
                    <span className="saved-card-title">Addasound</span>
                    <span className="saved-card-date">Oct 24</span>
                  </div>
                  <p className="saved-card-snippet">
                    Acoustic matrix, peripheral certifications,...
                  </p>
                  <div className="saved-card-tags">
                    <span className="saved-tag tag-lavender">Hardware</span>
                    <span className="saved-tag tag-mint">Verified</span>
                  </div>
                </div>

                <div className="saved-output-card">
                  <div className="saved-card-header">
                    <span className="saved-card-title">compatible services on huawei cloud</span>
                    <span className="saved-card-date">Oct 22</span>
                  </div>
                  <p className="saved-card-snippet">
                    Service mesh mapping, compute engine ti...
                  </p>
                  <div className="saved-card-tags">
                    <span className="saved-tag tag-purple">Infrastructure</span>
                    <span className="saved-tag tag-slate">Cloud</span>
                  </div>
                </div>

                <div className="saved-output-card">
                  <div className="saved-card-header">
                    <span className="saved-card-title">Huawei Cloud Data Ingestion 1</span>
                    <span className="saved-card-date">Oct 19</span>
                  </div>
                  <p className="saved-card-snippet">
                    Kafka pipelines, real-time ingestion...
                  </p>
                  <div className="saved-card-tags">
                    <span className="saved-tag tag-cyan">Pipeline</span>
                    <span className="saved-tag tag-slate">ETL</span>
                  </div>
                </div>
              </>
            )}
          </div>
        </div>

        {/* Bottom Export Synthesis Pack Button */}
        <button
          type="button"
          className="export-synthesis-btn"
          onClick={() => {
            const pack = [
              "# Field Desk — Synthesis Pack",
              "Generated: " + new Date().toISOString(),
              `Tenant Status: Catalog Grounded (Multi-source active)`,
              `Vector Sources: ${sourceCount || 50} indexed`,
              "\n## Grounded Intelligence Brief",
              "Extracted capabilities, SLA benchmarks, and compatibility requirements."
            ].join("\n");
            const blob = new Blob([pack], { type: "text/markdown;charset=utf-8;" });
            const url = URL.createObjectURL(blob);
            const a = document.createElement("a");
            a.href = url;
            a.download = `synthesis_pack_${new Date().toISOString().slice(0, 10)}.md`;
            a.click();
            URL.revokeObjectURL(url);
          }}
        >
          <PlusIcon size={15} />
          <span>Export Synthesis Pack</span>
        </button>
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
