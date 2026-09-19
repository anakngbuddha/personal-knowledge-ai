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
  if (loading) return <p className="muted">Loading documents...</p>;
  if (documents.length === 0) return <p className="muted">No documents yet. Upload a PDF, TXT, or DOCX.</p>;

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
      {documents.map((doc) => (
        <li
          key={doc.id}
          className={doc.id === selectedId ? "doc selected" : "doc"}
          onClick={() => onSelect(doc.id)}
        >
          <div className="doc-row">
            <span className="doc-name" title={doc.original_filename}>
              {doc.original_filename}
            </span>
            <span className={`badge ${doc.status}`}>{doc.status}</span>
          </div>
          <div className="doc-meta">
            {formatSize(doc.file_size)}
            {doc.page_count ? ` · ${doc.page_count} pages` : ""}
            {doc.chunk_count ? ` · ${doc.chunk_count} chunks` : ""}
          </div>
          {doc.error_message && <div className="doc-error">{doc.error_message}</div>}
          <div className="doc-actions">
            {doc.status === "failed" && (
              <button onClick={(e) => { e.stopPropagation(); void reprocess(doc.id); }}>Retry</button>
            )}
            <button onClick={(e) => { e.stopPropagation(); void remove(doc.id); }}>Delete</button>
          </div>
        </li>
      ))}
    </ul>
  );
}
