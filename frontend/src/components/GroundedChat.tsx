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
      });

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
      {/* Sidebar: Conversations & Source Toggling */}
      <aside className="chat-sidebar">
        <div className="sidebar-head">
          <h3>Conversations</h3>
          <button
            className="new-conv-btn"
            onClick={() => {
              setSelectedConvId(null);
              setCurrentConv(null);
            }}
          >
            + New
          </button>
        </div>

        <div className="conv-list">
          {conversations.length === 0 ? (
            <div className="empty-conv">No past conversations</div>
          ) : (
            conversations.map((c) => (
              <div
                key={c.id}
                className={`conv-item ${selectedConvId === c.id ? "active" : ""}`}
                onClick={() => setSelectedConvId(c.id)}
              >
                <div className="conv-title">{c.title || "Untitled conversation"}</div>
                <button
                  className="conv-delete"
                  title="Delete thread"
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

        {/* Source Toggling Panel */}
        {activeSources.length > 0 && (
          <div className="source-toggle-panel">
            <h4>Collateral Sources ({activeSources.length})</h4>
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

      {/* Main Chat Area */}
      <main className="chat-main">
        {error && <div className="banner error">{error}</div>}

        <div className="messages-stream">
          {!currentConv || currentConv.messages.length === 0 ? (
            <div className="chat-welcome">
              <h3>Ask Grounded Solution Engineering Questions</h3>
              <p>
                Answers are synthesized strictly from approved collateral, with every assertion
                accompanied by a citation anchor (page, slide, sheet) and provenance flags.
              </p>
            </div>
          ) : (
            currentConv.messages.map((msg) => (
              <div key={msg.id} className={`chat-message ${msg.role}`}>
                <div className="message-header">
                  <span className="role-label">
                    {msg.role === "user" ? "You" : "Personal Knowledge AI"}
                  </span>
                  {msg.model_id && (
                    <span className="model-label">
                      {msg.model_id} · v{msg.prompt_version}
                    </span>
                  )}
                </div>

                {msg.refused && (
                  <div className="refusal-banner">
                    Insufficient evidence in collateral to answer this query definitively.
                  </div>
                )}

                <div className="message-body">{msg.content}</div>

                {msg.citations && msg.citations.length > 0 && (
                  <div className="citations-tray">
                    <span className="citations-label">Sources:</span>
                    {msg.citations.map((c, i) => (
                      <button
                        key={i}
                        className={`citation-tag ${selectedCitation?.chunk_id === c.chunk_id ? "active" : ""}`}
                        onClick={() => setSelectedCitation(c)}
                      >
                        [{i + 1}] {c.citation}
                        {c.vendor && ` (${c.vendor})`}
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
              <div className="role-label">Synthesizing Grounded Answer...</div>
              <div className="loading-indicator">Searching collateral, enforcing permissions, and citing claims...</div>
            </div>
          )}
        </div>

        {/* Selected Citation Drawer */}
        {selectedCitation && (
          <div className="citation-drawer">
            <div className="drawer-head">
              <h4>Citation Detail: {selectedCitation.citation}</h4>
              <button onClick={() => setSelectedCitation(null)}>×</button>
            </div>
            <div className="drawer-content">
              <div><strong>Document:</strong> {selectedCitation.document_title || "Unknown"}</div>
              <div><strong>Vendor:</strong> {selectedCitation.vendor || "Internal"}</div>
              <div><strong>Approval:</strong> {selectedCitation.approval_state || "Draft"}</div>
              <div><strong>Freshness:</strong> {selectedCitation.is_stale ? "Overdue / Stale" : "Fresh"}</div>
              {selectedCitation.page_number && <div><strong>Page:</strong> {selectedCitation.page_number}</div>}
              {selectedCitation.slide_number && <div><strong>Slide:</strong> {selectedCitation.slide_number}</div>}
              {selectedCitation.sheet_name && <div><strong>Sheet:</strong> {selectedCitation.sheet_name} ({selectedCitation.cell_range})</div>}
            </div>
          </div>
        )}

        {/* Prompt Input */}
        <form onSubmit={handleSend} className="chat-input-form">
          <input
            type="text"
            className="chat-input"
            placeholder="Ask a question about products, compatibility, or RFP requirements..."
            value={question}
            onChange={(e) => setQuestion(e.target.value)}
            disabled={loading}
          />
          <button type="submit" className="primary" disabled={loading || !question.trim()}>
            Send
          </button>
        </form>
      </main>
    </div>
  );
}
