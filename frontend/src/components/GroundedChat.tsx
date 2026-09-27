import { useEffect, useRef, useState } from "react";
import { AssistantMarkdown } from "./AssistantMarkdown";
import {
  ArrowRightIcon,
  BookOpenIcon,
  FileTextIcon,
  InfoIcon,
  PaperclipIcon,
  SendIcon,
} from "./Icons";
import { NotebookPicker } from "./NotebookPicker";
import { api } from "../services/api";
import { askWithConversationRecovery } from "../services/askRecovery";
import type { Conversation, NotebookSource, SourceMetadata, StudioResult } from "../types";

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
  const [studio, setStudio] = useState<StudioResult | null>(null);
  const [studioBusy, setStudioBusy] = useState(false);
  const [sourcesExpertKnowledge, setSourcesExpertKnowledge] = useState(true);
  const [webSearchEnabled, setWebSearchEnabled] = useState(true);
  const notebookRef = useRef<string | null>(null);
  const selectedConversationRef = useRef<string | null>(null);
  const attachmentInputRef = useRef<HTMLInputElement | null>(null);
  const [attachedDocuments, setAttachedDocuments] = useState<{id:string; name:string}[]>([]);
  const [uploadingAttachment, setUploadingAttachment] = useState(false);
  const [resolvedActions, setResolvedActions] = useState<Record<string, string>>({});
  const [activeFilter, setActiveFilter] = useState<"briefing" | "faq" | "compare" | null>(null);

  useEffect(() => {
    void loadConversations(notebookId);
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
      if (notebookRef.current === id) setConversations(res.conversations);
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

  async function attachFiles(files: FileList | null) {
    if (!files?.length) return;
    const targetNotebookId = notebookRef.current;
    setUploadingAttachment(true);
    setError(null);
    try {
      const uploaded = await api.uploadDocuments(Array.from(files));
      const additions = uploaded.results.filter((item) => item.document_id && item.status !== "rejected")
        .map((item) => ({id: item.document_id!, name: item.original_filename}));
      if (!additions.length) throw new Error(uploaded.results.map((item) => item.detail).filter(Boolean).join("; ") || "No files were attached");
      if (targetNotebookId && notebookRef.current === targetNotebookId) {
        const ids = [...new Set([...enabledIds(), ...additions.map((item) => item.id)])];
        const saved = await api.setNotebookSources(targetNotebookId, ids);
        if (notebookRef.current === targetNotebookId) setSources(saved);
      }
      if (notebookRef.current === targetNotebookId) setAttachedDocuments((current) => [...current, ...additions]);
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
    const sentNotebookId = notebookId;
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
          notebook_id: sentNotebookId,
          attachment_document_ids: attachedDocuments.map((item) => item.id),
          filters: { document_ids: enabledIds() },
          enable_tools: true,
          strict_mode: strictMode,
          web_search: webSearchEnabled ? undefined : false,
        },
        (delta) => { if (delta) streamedAny = true; setStreamText(delta); },
        setStatusNote
      );
      const answer = await askWithConversationRecovery(sentConversationId, request,
        () => !streamedAny && notebookRef.current === sentNotebookId, () => {
        selectedConversationRef.current = null;
        setSelectedConvId(null);
        setCurrentConv(null);
      });
      if (notebookRef.current !== sentNotebookId) return;
      setWebSources(answer.web_sources || []);
      setWebNote(answer.web_note || null);
      setLastToolCalls((answer.tool_calls || []).map((c) => c.name));
      if ((!sentConversationId || selectedConversationRef.current === null) && answer.conversation_id) {
        selectedConversationRef.current = answer.conversation_id;
        setSelectedConvId(answer.conversation_id);
        await loadConversations(sentNotebookId);
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
      await loadConversations(notebookId);
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
      await api.createNote({
        title: studio.source_titles[0] ? `Note: ${studio.source_titles[0]}` : "Saved answer",
        body: studio.markdown,
        notebook_id: notebookId ?? undefined,
      });
      setStudio(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not save that note");
    } finally {
      setStudioBusy(false);
    }
  }

  const noThread = !currentConv || currentConv.messages.length === 0;

  return (
    <div className={`ask-desk ${selectedCitation || studio ? "inspector-open" : ""}`}>
      {/* ── Left Column: Workspace Sidebar ─────────────────────────────── */}
      <aside className="ask-sources">

        {/* Notebook Picker */}
        <NotebookPicker
          notebookId={notebookId}
          onChange={(id) => {
            notebookRef.current = id;
            selectedConversationRef.current = null;
            setNotebookId(id);
            setSelectedConvId(null);
            setCurrentConv(null);
            setAttachedDocuments([]);
          }}
        />

        <button type="button" className="ask-add-sources" onClick={() => onNavigate("sources")}>
          <FileTextIcon size={15} /> Manage sources
        </button>

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
            {conversations.map((c) => (
              <div key={c.id} className={`conv-item ${selectedConvId === c.id ? "active" : ""}`}>
                <button type="button" className="conv-open" onClick={() => { selectedConversationRef.current = c.id; setSelectedConvId(c.id); }}>
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
              <h2 className="welcome-title">
                Ask your knowledge
              </h2>
              <p className="welcome-subtitle">
                Get answers grounded in your sources and notes.
              </p>

              <div className="prompt-cards-container">
                {[
                  "Summarize key capabilities across all sources",
                  "Compare specifications from my uploaded documents",
                  "Extract requirements mentioned in my sources",
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
