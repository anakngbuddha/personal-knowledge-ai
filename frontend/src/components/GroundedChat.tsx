import { useEffect, useState } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { api } from "../services/api";
import type { AskResponse, Conversation, SourceMetadata } from "../types";

export function GroundedChat() {
  const [conversations, setConversations] = useState<Conversation[]>([]);
  const [selectedConvId, setSelectedConvId] = useState<string | null>(null);
  const [currentConv, setCurrentConv] = useState<Conversation | null>(null);
  const [question, setQuestion] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [selectedCitation, setSelectedCitation] = useState<SourceMetadata | null>(null);
  const [excludedDocIds, setExcludedDocIds] = useState<string[]>([]);
  const [activeSources, setActiveSources] = useState<SourceMetadata[]>([]);
  const [enableTools, setEnableTools] = useState(false);
  const [strictMode, setStrictMode] = useState(false);
  const [lastToolCalls, setLastToolCalls] = useState<string[]>([]);

  useEffect(() => {
    loadConversations();
  }, []);

  useEffect(() => {
    if (selectedConvId) {
      loadConversationDetails(selectedConvId);
      loadConversationSources(selectedConvId);
    } else {
      setCurrentConv(null);
      setActiveSources([]);
    }
  }, [selectedConvId]);

  async function loadConversations() {
    try {
      const res = await api.listConversations(30, 0);
      setConversations(res.conversations);
    } catch {
      /* ignore background error */
    }
  }

  async function loadConversationDetails(id: string) {
    try {
      const conv = await api.getConversation(id);
      setCurrentConv(conv);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load conversation");
    }
  }

  async function loadConversationSources(id: string) {
    try {
      const sources = await api.getConversationSources(id);
      setActiveSources(sources);
    } catch {
      /* non-critical */
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

    try {
      const answer: AskResponse = await api.ask({
        question: q,
        conversation_id: selectedConvId,
        exclude_document_ids: excludedDocIds,
        enable_tools: enableTools,
        strict_mode: strictMode,
      });
      setLastToolCalls((answer.tool_calls || []).map((c) => c.name));

      if (!selectedConvId && answer.conversation_id) {
        setSelectedConvId(answer.conversation_id);
        await loadConversations();
      } else if (selectedConvId) {
        await loadConversationDetails(selectedConvId);
        await loadConversationSources(selectedConvId);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Generation failed");
    } finally {
      setLoading(false);
    }
  }

  async function handleDelete(id: string) {
    try {
      await api.deleteConversation(id);
      if (selectedConvId === id) {
        setSelectedConvId(null);
      }
      await loadConversations();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to delete conversation");
    }
  }

  function toggleExcludeDoc(docId: string) {
    setExcludedDocIds((prev) =>
      prev.includes(docId) ? prev.filter((id) => id !== docId) : [...prev, docId]
    );
  }

  return (
    <div className="grounded-chat">
      <aside className="chat-sidebar">
        <div className="sidebar-head">
          <h3>Threads</h3>
          <button
            type="button"
            className="new-conv-btn"
            onClick={() => {
              setSelectedConvId(null);
              setCurrentConv(null);
            }}
          >
            New
          </button>
        </div>

        <div className="conv-list">
          {conversations.length === 0 ? (
            <div className="empty-conv">No threads yet. Start by asking a question.</div>
          ) : (
            conversations.map((c) => (
              <div
                key={c.id}
                className={`conv-item ${selectedConvId === c.id ? "active" : ""}`}
              >
                <button
                  type="button"
                  className="conv-open"
                  onClick={() => setSelectedConvId(c.id)}
                >
                  <span className="conv-title">{c.title || "Untitled"}</span>
                </button>
                <button
                  type="button"
                  className="conv-delete"
                  title="Delete"
                  aria-label="Delete"
                  onClick={(e) => {
                    e.stopPropagation();
                    handleDelete(c.id);
                  }}
                >
                  ×
                </button>
              </div>
            ))
          )}
        </div>

        {activeSources.length > 0 && (
          <div className="source-toggle-panel">
            <h4>Sources ({activeSources.length})</h4>
            <div className="source-list">
              {activeSources.map((src) => {
                const isExcluded = excludedDocIds.includes(src.document_id);
                return (
                  <div key={src.chunk_id} className={`source-item ${isExcluded ? "excluded" : ""}`}>
                    <label className="source-label">
                      <input
                        type="checkbox"
                        checked={!isExcluded}
                        onChange={() => toggleExcludeDoc(src.document_id)}
                      />
                      <span className="source-name">
                        {src.document_title || src.citation}
                      </span>
                    </label>
                    {src.is_stale && <span className="stale-badge">Stale</span>}
                  </div>
                );
              })}
            </div>
          </div>
        )}
      </aside>

      <main className="chat-main">
        {error && <div className="banner error">{error}</div>}

        <div className="messages-stream">
          {!currentConv || currentConv.messages.length === 0 ? (
            <div className="chat-welcome">
              <h2>Knowledge Advisor</h2>
              <p>
                Upload your documents, then ask questions. Get answers with citations from your sources or expert knowledge.
              </p>
            </div>
          ) : (
            currentConv.messages.map((msg) => (
              <div key={msg.id} className={`chat-message ${msg.role}`}>
                <div className="message-header">
                  <span className="role-label">
                    {msg.role === "user" ? "You" : "Assistant"}
                  </span>
                  {msg.model_id && (
                    <span className="model-label">
                      {msg.model_id} · v{msg.prompt_version}
                    </span>
                  )}
                </div>

                <div className="message-body markdown-body">
                  <ReactMarkdown remarkPlugins={[remarkGfm]}>
                    {msg.content}
                  </ReactMarkdown>
                </div>

                {msg.role === "assistant" && lastToolCalls.length > 0 && (
                  <div className="tool-calls-tray">
                    Used: {lastToolCalls.join(", ")}
                  </div>
                )}

                {msg.citations && msg.citations.length > 0 && (
                  <div className="citations-tray">
                    <span className="citations-label">Sources</span>
                    {msg.citations.map((c, i) => (
                      <button
                        key={i}
                        type="button"
                        className={`citation-tag ${selectedCitation?.chunk_id === c.chunk_id ? "active" : ""}`}
                        onClick={() => setSelectedCitation(c)}
                      >
                        [{i + 1}] {c.citation}
                        {c.vendor && <span className="vendor-tag"> · {c.vendor}</span>}
                        {c.is_stale && <span className="stale-indicator">●</span>}
                      </button>
                    ))}
                  </div>
                )}
              </div>
            ))
          )}

          {loading && (
            <div className="chat-message assistant loading">
              <div className="role-label">Thinking…</div>
              <div className="loading-indicator">Searching sources and generating answer…</div>
            </div>
          )}
        </div>

        {selectedCitation && (
          <div className="citation-drawer">
            <div className="drawer-head">
              <h4>{selectedCitation.citation}</h4>
              <button type="button" onClick={() => setSelectedCitation(null)} aria-label="Close">
                ×
              </button>
            </div>
            <div className="drawer-content">
              <strong>Document</strong>
              <span>{selectedCitation.document_title || "Unknown"}</span>
              <strong>Vendor</strong>
              <span>{selectedCitation.vendor || "—"}</span>
              <strong>Status</strong>
              <span>{selectedCitation.approval_state || "Draft"}</span>
              <strong>Freshness</strong>
              <span>{selectedCitation.is_stale ? "Stale" : "Fresh"}</span>
              {selectedCitation.page_number && (
                <>
                  <strong>Page</strong>
                  <span>{selectedCitation.page_number}</span>
                </>
              )}
              {selectedCitation.slide_number && (
                <>
                  <strong>Slide</strong>
                  <span>{selectedCitation.slide_number}</span>
                </>
              )}
              {selectedCitation.sheet_name && (
                <>
                  <strong>Sheet</strong>
                  <span>
                    {selectedCitation.sheet_name} ({selectedCitation.cell_range})
                  </span>
                </>
              )}
            </div>
          </div>
        )}

        <form onSubmit={handleSend} className="chat-input-form">
          <div className="form-options">
            <label className="checkbox-option">
              <input
                type="checkbox"
                checked={strictMode}
                onChange={(e) => setStrictMode(e.target.checked)}
              />
              Strict mode (sources only)
            </label>
            <label className="checkbox-option">
              <input
                type="checkbox"
                checked={enableTools}
                onChange={(e) => setEnableTools(e.target.checked)}
                disabled={loading}
              />
              Enable tools & web search
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
            <button type="submit" className="primary" disabled={loading || !question.trim()}>
              {loading ? "…" : "Send"}
            </button>
          </div>
        </form>
      </main>
    </div>
  );
}
