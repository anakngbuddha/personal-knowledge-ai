import { useEffect, useState } from "react";
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
          <h3>Thread log</h3>
          <button
            type="button"
            className="new-conv-btn"
            onClick={() => {
              setSelectedConvId(null);
              setCurrentConv(null);
            }}
          >
            New thread
          </button>
        </div>

        <div className="conv-list">
          {conversations.length === 0 ? (
            <div className="empty-conv">No threads on this desk yet. Open one with a grounded question.</div>
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
                  <span className="conv-title">{c.title || "Untitled thread"}</span>
                </button>
                <button
                  type="button"
                  className="conv-delete"
                  title="Delete thread"
                  aria-label="Delete thread"
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
            <h4>Collateral in play ({activeSources.length})</h4>
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
                    <span className={`badge ${src.is_stale ? "stale" : "fresh"}`}>
                      {src.is_stale ? "Stale" : "Fresh"}
                    </span>
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
              <p className="kicker">04 · Grounded desk</p>
              <h3>Ask against approved collateral only.</h3>
              <p>
                Every assertion must carry a citation — page, slide, or sheet. Uncited claims are
                refused. Treat this like a live deal room, not a chat toy.
              </p>
            </div>
          ) : (
            currentConv.messages.map((msg) => (
              <div key={msg.id} className={`chat-message ${msg.role}`}>
                <div className="message-header">
                  <span className="role-label">
                    {msg.role === "user" ? "Query" : "Grounded"}
                  </span>
                  {msg.model_id && (
                    <span className="model-label">
                      {msg.model_id} · v{msg.prompt_version}
                    </span>
                  )}
                </div>

                {msg.refused && (
                  <div className="refusal-banner">
                    Insufficient evidence in collateral — claim withheld.
                  </div>
                )}

                <div className="message-body">{msg.content}</div>

                {msg.role === "assistant" && lastToolCalls.length > 0 && (
                  <div className="tool-calls-tray">
                    Tools dispatched: {lastToolCalls.join(", ")}
                  </div>
                )}

                {msg.citations && msg.citations.length > 0 && (
                  <div className="citations-tray">
                    <span className="citations-label">Cited</span>
                    {msg.citations.map((c, i) => (
                      <button
                        key={i}
                        type="button"
                        className={`citation-tag ${selectedCitation?.chunk_id === c.chunk_id ? "active" : ""}`}
                        onClick={() => setSelectedCitation(c)}
                      >
                        [{i + 1}] {c.citation}
                        {c.vendor && ` · ${c.vendor}`}
                        {c.approval_state ? ` · ${c.approval_state}` : ""}
                        {c.is_stale && <span className="stale-dot" title="Stale document">●</span>}
                      </button>
                    ))}
                  </div>
                )}
              </div>
            ))
          )}

          {loading && (
            <div className="chat-message assistant loading">
              <div className="role-label">Synthesizing</div>
              <div className="loading-indicator">
                Searching collateral, enforcing permissions, citing claims…
              </div>
            </div>
          )}
        </div>

        {selectedCitation && (
          <div className="citation-drawer">
            <div className="drawer-head">
              <h4>{selectedCitation.citation}</h4>
              <button type="button" onClick={() => setSelectedCitation(null)} aria-label="Close citation">
                ×
              </button>
            </div>
            <div className="drawer-content">
              <strong>Document</strong>
              <span>{selectedCitation.document_title || "Unknown"}</span>
              <strong>Vendor</strong>
              <span>{selectedCitation.vendor || "Internal"}</span>
              <strong>Approval</strong>
              <span>{selectedCitation.approval_state || "Draft"}</span>
              <strong>Freshness</strong>
              <span>{selectedCitation.is_stale ? "Overdue / stale" : "Fresh"}</span>
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
          <label className="tools-toggle">
            <input
              type="checkbox"
              checked={enableTools}
              onChange={(e) => setEnableTools(e.target.checked)}
            />
            Tools (catalog + MCP)
          </label>
          <input
            type="text"
            className="chat-input"
            placeholder="Compatibility, SLA, RFP clause, upgrade path…"
            value={question}
            onChange={(e) => setQuestion(e.target.value)}
            disabled={loading}
          />
          <button type="submit" className="primary" disabled={loading || !question.trim()}>
            Dispatch
          </button>
        </form>
      </main>
    </div>
  );
}
