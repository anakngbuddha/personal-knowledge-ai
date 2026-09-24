import { useEffect, useState } from "react";
import { AssistantMarkdown } from "./AssistantMarkdown";
import { BookOpenIcon, SendIcon, SparklesIcon } from "./Icons";
import { NotebookPicker } from "./NotebookPicker";
import { WorkflowWorkspace } from "./WorkflowWorkspace";
import { api } from "../services/api";
import type { Conversation, NoteRecord, NotebookSource, SourceMetadata, StudioResult } from "../types";

interface Props {
  sourceCount: number;
  onNavigate: (tab: "sources" | "map") => void;
}

export function GroundedChat({ sourceCount, onNavigate }: Props) {
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
      <aside className="ask-sources">
        <NotebookPicker
          notebookId={notebookId}
          onChange={(id) => {
            setNotebookId(id);
            setSelectedConvId(null);
            setCurrentConv(null);
          }}
        />
        <h3>Sources</h3>
        {sources.length === 0 ? (
          <div className="empty-state">
            <p>1. Add documents</p>
            <p>2. Add your products</p>
            <p>3. Ask</p>
            <button type="button" className="link-button" onClick={() => onNavigate("sources")}>
              Go to Sources
            </button>
            <button type="button" className="link-button" onClick={() => onNavigate("map")}>
              Go to Map
            </button>
          </div>
        ) : (
          <ul className="source-list">
            {sources.map((row) => (
              <li key={row.document_id}>
                <label>
                  <input type="checkbox" checked={row.enabled} onChange={() => void toggleSource(row.document_id)} />
                  <span>{row.title || row.filename}</span>
                </label>
              </li>
            ))}
          </ul>
        )}
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
        <h3>Threads</h3>
        {conversations.length === 0 ? (
          <p className="empty-copy">Ask a question to start a thread.</p>
        ) : (
          conversations.map((c) => (
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
          ))
        )}
      </aside>

      <main className="ask-chat">
        {error && <div className="banner error">{error}</div>}
        {sourceCount === 0 && (
          <div className="banner info">1. Add documents. 2. Add your products. 3. Ask.</div>
        )}
        <div className="messages-stream">
          {noThread && !loading ? (
            <div className="chat-welcome">
              <div
                style={{
                  width: 44,
                  height: 44,
                  borderRadius: 12,
                  background: "linear-gradient(135deg, rgba(99, 102, 241, 0.2), rgba(6, 182, 212, 0.2))",
                  border: "1px solid var(--primary-border)",
                  display: "flex",
                  alignItems: "center",
                  justifyContent: "center",
                  color: "var(--primary)",
                  boxShadow: "0 0 20px var(--primary-glow)",
                  marginBottom: 4,
                }}
              >
                <SparklesIcon size={24} />
              </div>
              <h2>How can I help you today?</h2>
              <p>
                Ask questions grounded directly in your uploaded documentation, product catalogs, and team notes.
              </p>
              <div
                style={{
                  display: "grid",
                  gridTemplateColumns: "repeat(auto-fit, minmax(220px, 1fr))",
                  gap: 10,
                  width: "100%",
                  marginTop: 12,
                }}
              >
                {[
                  "Summarize key capabilities across all sources",
                  "What are the deployment prerequisites & compatibility?",
                  "Compare pricing, licensing tiers & architecture",
                  "Draft an executive briefing for stakeholders",
                ].map((prompt) => (
                  <button
                    key={prompt}
                    type="button"
                    style={{
                      padding: "12px 14px",
                      borderRadius: 10,
                      background: "var(--bg-card)",
                      border: "1px solid var(--rule-strong)",
                      color: "var(--text-primary)",
                      textAlign: "left",
                      fontSize: "12.5px",
                      lineHeight: "1.4",
                      cursor: "pointer",
                      transition: "all 160ms var(--ease-out)",
                      display: "flex",
                      flexDirection: "column",
                      gap: 4,
                    }}
                    onClick={() => setQuestion(prompt)}
                  >
                    <span style={{ fontSize: "10px", color: "var(--primary)", fontFamily: "var(--font-mono)", fontWeight: 600 }}>PROMPT</span>
                    <span>{prompt}</span>
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
        <form onSubmit={handleSend} className="chat-input-form">
          <div className="form-options">
            <label className="checkbox-option">
              <input type="checkbox" checked={strictMode} onChange={(e) => setStrictMode(e.target.checked)} />
              {strictMode ? "From my sources only" : "Sources + expert knowledge"}
            </label>
          </div>
          <div className="input-group">
            <input
              type="text"
              className="chat-input"
              placeholder="Ask about compatibility, pricing, requirements…"
              value={question}
              onChange={(e) => setQuestion(e.target.value)}
              disabled={loading}
            />
            <button type="submit" className="primary" disabled={loading || !question.trim()} style={{ display: "inline-flex", alignItems: "center", gap: 6, padding: "10px 18px", borderRadius: 10 }}>
              {loading ? "…" : (
                <>
                  <span>Send</span>
                  <SendIcon size={14} />
                </>
              )}
            </button>
          </div>
        </form>
        <details className="suggested-actions">
          <summary>Suggested actions</summary>
          <WorkflowWorkspace />
        </details>
      </main>

      <aside className="ask-side">
        <h3>Citation</h3>
        {selectedCitation ? (
          <div className="citation-drawer">
            <strong>{selectedCitation.citation}</strong>
            <p>{selectedCitation.document_title || "Source"}</p>
            <p>{selectedCitation.vendor || "Vendor not listed"}</p>
            {selectedCitation.page_number ? <p>Page {selectedCitation.page_number}</p> : null}
          </div>
        ) : (
          <p className="empty-copy">Citations you open will show here.</p>
        )}
        {studio && (
          <div className="saved-output">
            <AssistantMarkdown text={studio.markdown} citations={[]} onSelect={() => undefined} />
            <button type="button" disabled={studioBusy} onClick={() => void saveStudio()}>
              Save as note
            </button>
          </div>
        )}
        <h3>Saved outputs</h3>
        {savedNotes.length === 0 ? (
          <p className="empty-copy">Briefs and saved answers for this notebook show up here.</p>
        ) : (
          <ul className="note-index">
            {savedNotes.map((note) => (
              <li key={note.id}>
                <strong>{note.title}</strong>
              </li>
            ))}
          </ul>
        )}
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
