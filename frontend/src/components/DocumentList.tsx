import React, { useState } from "react";
import { CheckIcon, FileTextIcon, RefreshCwIcon, TrashIcon } from "./Icons";
import { api } from "../services/api";
import type { KnowledgeDocument } from "../types";

interface Props {
  documents: KnowledgeDocument[];
  loading: boolean;
  selectedId: string | null;
  onSelect: (id: string) => void;
  onChanged: () => void;
  onError: (message: string) => void;
}

function formatSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(0)} KB`;
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`;
}

export function DocumentList({
  documents,
  loading,
  selectedId,
  onSelect,
  onChanged,
  onError,
}: Props) {
  const [pendingDelete, setPendingDelete] = useState<string | null>(null);

  if (loading) {
    return (
      <div style={{ padding: "24px 12px", textAlign: "center", color: "var(--text-muted)" }}>
        <p className="muted">Retrieving documents from vector storage…</p>
      </div>
    );
  }

  if (documents.length === 0) {
    return (
      <div className="empty-desk" style={{ borderLeftColor: "var(--primary)" }}>
        <p className="kicker">Knowledge Library Empty</p>
        <h3 style={{ fontSize: "20px" }}>No documents indexed yet</h3>
        <p>
          Upload PDF guides, datasheets, spreadsheets, or Markdown notes above to populate your workspace knowledge graph.
        </p>
      </div>
    );
  }

  async function remove(id: string) {
    try {
      await api.deleteDocument(id);
      onChanged();
    } catch (err) {
      onError(err instanceof Error ? err.message : "delete failed");
    }
  }

  async function reprocess(id: string) {
    try {
      await api.reprocessDocument(id);
      onChanged();
    } catch (err) {
      onError(err instanceof Error ? err.message : "reprocess failed");
    }
  }

  return (
    <ul className="doc-list">
      {documents.map((doc) => {
        const isSelected = doc.id === selectedId;
        return (
          <li
            key={doc.id}
            className={isSelected ? "doc selected" : "doc"}
            onClick={() => onSelect(doc.id)}
            onKeyDown={(e) => {
              if (e.key === "Enter" || e.key === " ") {
                e.preventDefault();
                onSelect(doc.id);
              }
            }}
            role="button"
            tabIndex={0}
          >
            <div className="doc-row">
              <div style={{ display: "flex", alignItems: "center", gap: 10, minWidth: 0 }}>
                <span style={{ color: isSelected ? "var(--primary)" : "var(--text-muted)" }}>
                  <FileTextIcon size={16} />
                </span>
                <span className="doc-name" title={doc.original_filename}>
                  {doc.original_filename}
                </span>
              </div>
              <span className={`badge ${doc.status}`}>{doc.status}</span>
            </div>

            <div className="doc-meta">
              <span>{formatSize(doc.file_size)}</span>
              {doc.page_count ? <span>{doc.page_count} pp</span> : null}
              {doc.ocr_applied ? <span>OCR</span> : null}
              {doc.vendor ? <span>{doc.vendor}</span> : null}
              {doc.chunk_count ? <span>{doc.chunk_count} chunks</span> : null}
              {doc.approval_state === "approved" ? (
                <span style={{ color: "var(--forest-text)" }}>Ready</span>
              ) : null}
            </div>

            {doc.error_message && <div className="doc-error">{doc.error_message}</div>}

            <div className="doc-actions" onClick={(e) => e.stopPropagation()}>
              {doc.status === "failed" && (
                <button
                  type="button"
                  onClick={() => void reprocess(doc.id)}
                  style={{ fontSize: "11px", padding: "4px 8px" }}
                >
                  <RefreshCwIcon size={12} />
                  <span>Retry</span>
                </button>
              )}
              <button
                type="button"
                style={{
                  fontSize: "11px",
                  padding: "4px 8px",
                  color: pendingDelete === doc.id ? "var(--signal-text)" : undefined,
                  borderColor: pendingDelete === doc.id ? "var(--signal-line)" : undefined,
                  background: pendingDelete === doc.id ? "var(--signal-soft)" : undefined,
                }}
                onClick={() => {
                  if (pendingDelete !== doc.id) {
                    setPendingDelete(doc.id);
                    return;
                  }
                  setPendingDelete(null);
                  void remove(doc.id);
                }}
                onBlur={() => setPendingDelete((current) => (current === doc.id ? null : current))}
              >
                {pendingDelete === doc.id ? (
                  <>
                    <CheckIcon size={12} />
                    <span>Confirm delete</span>
                  </>
                ) : (
                  <>
                    <TrashIcon size={12} />
                    <span>Delete</span>
                  </>
                )}
              </button>
            </div>
          </li>
        );
      })}
    </ul>
  );
}
