import { useEffect, useRef, useState } from "react";
import { AssistantMarkdown } from "./AssistantMarkdown";
import {
  ArrowRightIcon,
  BookOpenIcon,
  FileTextIcon,
  HistoryIcon,
  InfoIcon,
  PaperclipIcon,
  PlusIcon,
  SendIcon,
} from "./Icons";
import { api } from "../services/api";
import { askWithConversationRecovery } from "../services/askRecovery";
import type { Conversation, SourceMetadata, StudioResult } from "../types";

type Tab = "sources" | "ask" | "notes" | "map" | "connections" | "settings";

export interface TabItem {
  id: Tab;
  name: string;
  icon: React.ComponentType<{ size?: number }>;
  badge?: string;
}

interface Props {
  sourceCount: number;
  documentIds: string[];
  onNavigate: (tab: "sources" | "map") => void;
  activeTab?: Tab;
  onTabChange?: (tab: Tab) => void;
  tabs?: TabItem[];
  initialQuestion?: string | null;
}

export function GroundedChat({
  sourceCount,
  documentIds,
  onNavigate,
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
  const [studio, setStudio] = useState<StudioResult | null>(null);
  const [studioBusy, setStudioBusy] = useState(false);
  const [sourcesExpertKnowledge, setSourcesExpertKnowledge] = useState(true);
  const [webSearchEnabled, setWebSearchEnabled] = useState(true);
  const selectedConversationRef = useRef<string | null>(null);
  const attachmentInputRef = useRef<HTMLInputElement | null>(null);
  const [attachedDocuments, setAttachedDocuments] = useState<{id:string; name:string}[]>([]);
  const [uploadingAttachment, setUploadingAttachment] = useState(false);
  const [resolvedActions, setResolvedActions] = useState<Record<string, string>>({});
  const [activeFilter, setActiveFilter] = useState<"briefing" | "faq" | "compare" | null>(null);
  const [historyOpen, setHistoryOpen] = useState(false);

  useEffect(() => {
    void loadConversations();
    // History is loaded once when Ask opens. The server returns all workspace conversations.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    if (!historyOpen) return;
    const closeOnEscape = (event: KeyboardEvent) => {
      if (event.key === "Escape") setHistoryOpen(false);
    };
    window.addEventListener("keydown", closeOnEscape);
    return () => window.removeEventListener("keydown", closeOnEscape);
  }, [historyOpen]);

  useEffect(() => {
    if (selectedConvId) {
      void loadConversationDetails(selectedConvId);
    } else {
      setCurrentConv(null);
    }
  }, [selectedConvId]);

  async function loadConversations() {
    try {
      const res = await api.listConversations(30, 0);
      setConversations(res.conversations);
    } catch {
      /* keep the previous list */
    }
  }

  async function loadConversationDetails(id: string) {
    try {
      const conv = await api.getConversation(id);
      if (selectedConversationRef.current === id) setCurrentConv(conv);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not open that conversation");
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
      });
      setWebSources((prev) => prev.filter((item) => item.source_url !== source.source_url));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not add that page");
    } finally {
      setSavingUrl(null);
    }
  }

  async function attachFiles(files: FileList | null) {
    if (!files?.length) return;
    setUploadingAttachment(true);
    setError(null);
    try {
      const uploaded = await api.uploadDocuments(Array.from(files));
      const additions = uploaded.results.filter((item) => item.document_id && item.status !== "rejected")
        .map((item) => ({id: item.document_id!, name: item.original_filename}));
      if (!additions.length) throw new Error(uploaded.results.map((item) => item.detail).filter(Boolean).join("; ") || "No files were attached");
      setAttachedDocuments((current) => [...current, ...additions]);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not attach files");
    } finally {
      setUploadingAttachment(false);
      if (attachmentInputRef.current) attachmentInputRef.current.value = "";
    }
  }

  async function handleSend(e: React.FormEvent) {
    e.preventDefault();
    if (!question.trim() || loading) return;
    const q = question.trim();
    const sentConversationId = selectedConvId;
    setQuestion("");
    setLoading(true);
    setError(null);
    setSelectedCitation(null);
    setStreamText("");
    setStatusNote(null);
    setWebSources([]);
    setWebNote(null);
    let streamedAny = false;
    try {
      const request = (conversationId: string | null) => api.askStream(
        {
          question: q,
          conversation_id: conversationId,
          attachment_document_ids: attachedDocuments.map((item) => item.id),
          filters: { document_ids: [] },
          enable_tools: true,
          strict_mode: strictMode,
          web_search: webSearchEnabled ? undefined : false,
        },
        (delta) => { if (delta) streamedAny = true; setStreamText(delta); },
        setStatusNote
      );
      const answer = await askWithConversationRecovery(sentConversationId, request,
        () => !streamedAny, () => {
        selectedConversationRef.current = null;
        setSelectedConvId(null);
        setCurrentConv(null);
      });
      setWebSources(answer.web_sources || []);
      setWebNote(answer.web_note || null);
      setLastToolCalls((answer.tool_calls || []).map((c) => c.name));
      if ((!sentConversationId || selectedConversationRef.current === null) && answer.conversation_id) {
        selectedConversationRef.current = answer.conversation_id;
        setSelectedConvId(answer.conversation_id);
        await loadConversations();
      } else if (sentConversationId) {
        await loadConversationDetails(sentConversationId);
      }
      setStreamText("");
      setStatusNote(null);
      setAttachedDocuments([]);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not write an answer");
      setQuestion(q);
    } finally {
      setLoading(false);
    }
  }

  async function handleDelete(id: string) {
    try {
      await api.deleteConversation(id);
      if (selectedConvId === id) { selectedConversationRef.current = null; setSelectedConvId(null); }
      await loadConversations();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not delete that conversation");
    }
  }

  async function resolveAgentAction(id: string, confirm: boolean) {
    try {
      const result = confirm ? await api.confirmAgentAction(id) : await api.rejectAgentAction(id);
      setResolvedActions((current) => ({...current, [id]: result.status}));
      if (selectedConversationRef.current) await loadConversationDetails(selectedConversationRef.current);
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not resolve the action");
    }
  }

  async function runStudio(kind: "briefing" | "faq" | "compare") {
    const ids = documentIds;
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
      await api.createNote({
        title: studio.source_titles[0] ? `Note: ${studio.source_titles[0]}` : "Saved answer",
        body: studio.markdown,
      });
      setStudio(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not save that note");
    } finally {
      setStudioBusy(false);
    }
  }

  function startNewSession() {
    selectedConversationRef.current = null;
    setSelectedConvId(null);
    setCurrentConv(null);
    setQuestion("");
    setError(null);
    setSelectedCitation(null);
    setStudio(null);
    setWebSources([]);
    setWebNote(null);
    setAttachedDocuments([]);
    setHistoryOpen(false);
  }

  const noThread = !currentConv || currentConv.messages.length === 0;

  return (
    <div className={`ask-desk ${selectedCitation || studio ? "inspector-open" : ""}`}>
      <main className="ask-chat">
        <div className="ask-toolbar">
          <div className="ask-breadcrumbs">
            <span>Workspace</span>
            <ArrowRightIcon size={13} />
            <strong>Ask Intelligence</strong>
            <span className="ask-grounding-badge"><span /> Workspace knowledge</span>
          </div>
          <div className="ask-toolbar-actions">
            <button type="button" className="ask-tool-button" onClick={() => onNavigate("sources")}>
              <FileTextIcon size={16} /> <span>Manage sources</span>
            </button>
            <button
              type="button"
              className="ask-tool-button"
              onClick={() => setHistoryOpen(true)}
              aria-haspopup="dialog"
              aria-expanded={historyOpen}
            >
              <HistoryIcon size={16} /> <span>History</span>
            </button>
            <button type="button" className="ask-new-session" onClick={startNewSession}>
              <PlusIcon size={15} /> <span>New session</span>
            </button>
          </div>
        </div>
        {error && <div className="banner error">{error}</div>}
        <div className="messages-stream">
          {noThread && !loading ? (
            <div className="chat-welcome">
              <div className="welcome-grounding"><span /> Knowledge grounding active · {sourceCount} sources available</div>
              <h2 className="welcome-title">
                Ask your knowledge
              </h2>
              <p className="welcome-subtitle">
                Get answers grounded in your uploaded files and workspace knowledge.
              </p>

              <div className="prompt-cards-container">
                {[
                  "Summarize key capabilities across all sources",
                  "Compare specifications from my uploaded documents",
                  "Extract requirements mentioned in my sources",
                ].map((promptText, index) => (
                  <button
                    key={promptText}
                    type="button"
                    className="prompt-card-btn"
                    onClick={() => {
                      setQuestion(promptText);
                    }}
                  >
                    <div className="prompt-card-left">
                      <span className="prompt-badge">{["PROMPT · OVERVIEW", "PROMPT · COMPARISON", "PROMPT · EXTRACTION"][index]}</span>
                      <span className="prompt-text">{promptText}</span>
                    </div>
                    <ArrowRightIcon size={16} className="prompt-card-arrow" />
                  </button>
                ))}
              </div>
              <div className="studio-suggestions" aria-label="Quick source actions">
                {(["briefing", "faq", "compare"] as const).map((kind) => (
                  <button
                    key={kind}
                    type="button"
                    className={`thread-filter-btn ${activeFilter === kind ? "active" : ""}`}
                    disabled={studioBusy}
                    onClick={() => {
                      setActiveFilter(kind);
                      void runStudio(kind);
                    }}
                  >
                    {kind === "faq" ? "FAQ" : kind[0].toUpperCase() + kind.slice(1)}
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
                  <div className="agent-results">
                    {(msg.tool_calls || []).map((call) => {
                      const artifact = call.content?.artifact as {kind?:string; id?:string; title?:string} | undefined;
                      const pending = call.content?.pending_action as {id?:string; label?:string} | undefined;
                      return <div key={call.id} className="agent-result">
                        {call.error && <span>{call.name}: {call.error}</span>}
                        {artifact && <span>Created {artifact.kind}: {artifact.title || artifact.id} ({artifact.id})</span>}
                        {pending?.id && <div><span>{pending.label}</span>{" "}
                          {resolvedActions[pending.id] ? <span>{resolvedActions[pending.id]}</span> : <>
                            <button type="button" onClick={() => void resolveAgentAction(pending.id!, true)}>Confirm</button>{" "}
                            <button type="button" onClick={() => void resolveAgentAction(pending.id!, false)}>Reject</button>
                          </>}
                        </div>}
                      </div>;
                    })}
                  </div>
                )}
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
          <details className="answer-options">
            <summary>Answer options</summary>
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
              <span>Allow general knowledge (labelled separately)</span>
              <span className="info-circle" title="Use general knowledge only when clearly labelled apart from your sources">
                <InfoIcon size={13} />
              </span>
            </label>

            <div className="hybrid-rag-control">
              <span className="info-circle" title="Automatically perform live web search if information does not exist in knowledge base or to augment AI training data">
                <InfoIcon size={13} />
              </span>
              <span className="hybrid-rag-label">Web Search (Auto / Live)</span>
              <button
                type="button"
                className={`ios-toggle ${webSearchEnabled ? "active" : ""}`}
                role="switch"
                aria-checked={webSearchEnabled}
                onClick={() => setWebSearchEnabled(!webSearchEnabled)}
                title="Toggle Live Web Search"
              >
                <span className="ios-toggle-knob" />
              </button>
            </div>
            </div>
          </details>

          <div className="composer-bar-container">
            <input ref={attachmentInputRef} type="file" multiple hidden onChange={(e) => void attachFiles(e.target.files)} />
            <button
              type="button"
              className="composer-attach-btn"
              title="Attach document or note"
              aria-label="Attach source"
              onClick={() => attachmentInputRef.current?.click()}
            >
              <PaperclipIcon size={18} />
            </button>
            <input
              type="text"
              className="chat-pill-input"
              placeholder="Ask a question about your knowledge…"
              aria-label="Ask a question"
              value={question}
              onChange={(e) => setQuestion(e.target.value)}
              disabled={loading || uploadingAttachment}
            />
            <button
              type="submit"
              className="composer-send-btn"
              disabled={loading || uploadingAttachment || !question.trim()}
            >
              <span>Send</span>
              <SendIcon size={14} />
            </button>
          </div>

        </form>
      </main>

      {historyOpen && (
        <div className="history-drawer-layer">
          <button
            type="button"
            className="history-drawer-scrim"
            aria-label="Close chat history"
            onClick={() => setHistoryOpen(false)}
          />
          <aside className="history-drawer" role="dialog" aria-modal="true" aria-label="Chat history">
            <div className="history-drawer-header">
              <div>
                <span className="history-drawer-kicker">WORKSPACE</span>
                <h2>Chat history</h2>
              </div>
              <button type="button" className="history-close-button" onClick={() => setHistoryOpen(false)} aria-label="Close chat history">×</button>
            </div>
            <button type="button" className="history-new-session" onClick={startNewSession}>
              <PlusIcon size={15} /> New session
            </button>
            <div className="history-list">
              {conversations.length === 0 ? (
                <p className="history-empty">Your conversations will appear here.</p>
              ) : conversations.map((conversation) => (
                <div key={conversation.id} className={`history-item ${selectedConvId === conversation.id ? "active" : ""}`}>
                  <button
                    type="button"
                    className="history-item-open"
                    onClick={() => {
                      selectedConversationRef.current = conversation.id;
                      setSelectedConvId(conversation.id);
                      setHistoryOpen(false);
                    }}
                  >
                    <span>{conversation.title || "Untitled conversation"}</span>
                  </button>
                  <button
                    type="button"
                    className="history-item-delete"
                    aria-label={pendingDeleteId === conversation.id ? "Confirm delete conversation" : `Delete ${conversation.title || "conversation"}`}
                    onClick={() => {
                      if (pendingDeleteId !== conversation.id) {
                        setPendingDeleteId(conversation.id);
                        return;
                      }
                      setPendingDeleteId(null);
                      void handleDelete(conversation.id);
                    }}
                    onBlur={() => setPendingDeleteId((current) => current === conversation.id ? null : current)}
                  >
                    {pendingDeleteId === conversation.id ? "Confirm" : "×"}
                  </button>
                </div>
              ))}
            </div>
          </aside>
        </div>
      )}

      {/* ── Right Column: Citation Live Inspector & Saved Outputs ──────── */}
      {(selectedCitation || studio) && <aside className="ask-side">
        {/* Citation Live Inspector */}
        {selectedCitation && <div className="side-section citation-section">
          <div className="side-section-header">
            <span className="side-title">Source passage</span>
          </div>
          {attachedDocuments.length > 0 && <div className="attached-source-list">Attached: {attachedDocuments.map((item) => item.name).join(", ")}</div>}

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
        </div>}

        {studio && (
          <div className="saved-output">
            <AssistantMarkdown text={studio.markdown} citations={[]} onSelect={() => undefined} />
            <button type="button" disabled={studioBusy} onClick={() => void saveStudio()}>
              Save as note
            </button>
            <button type="button" onClick={() => setStudio(null)}>Close preview</button>
          </div>
        )}

      </aside>}
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
