import { useEffect, useState } from "react";

import { api } from "../services/api";
import type { DocumentChunk } from "../types";

interface Props {
  documentId: string | null;
}

/**
 * Phase 1 verification surface: proves chunk metadata (page, section, offsets, embedding)
 * survived ingestion. The grounded chat panel replaces the hero slot in Phase 3.
 */
export function ChunkInspector({ documentId }: Props) {
  const [chunks, setChunks] = useState<DocumentChunk[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (!documentId) {
      setChunks([]);
      return;
    }
    setLoading(true);
    api
      .listChunks(documentId)
      .then(setChunks)
      .catch((err: unknown) => setError(err instanceof Error ? err.message : "could not load chunks"))
      .finally(() => setLoading(false));
  }, [documentId]);

  if (!documentId) {
    return (
      <div className="empty-desk">
        <p className="kicker">Select</p>
        <h3>Pick a file from the dossier.</h3>
        <p>Chunks show page, section, citation, and whether a vector landed.</p>
      </div>
    );
  }
  if (loading) return <p className="muted">Loading chunks…</p>;
  if (error) return <p className="error">{error}</p>;
  if (chunks.length === 0) {
    return (
      <div className="empty-desk">
        <p className="kicker">Ingest</p>
        <h3>No chunks yet.</h3>
        <p>Ingestion may still be running. Refresh once status stamps ready.</p>
      </div>
    );
  }

  return (
    <div className="chunks">
      {chunks.map((chunk) => (
        <article key={chunk.id} className="chunk">
          <header>
            <span className="chunk-index">#{String(chunk.chunk_index).padStart(2, "0")}</span>
            {chunk.citation && <span className="tag">{chunk.citation}</span>}
            {chunk.page_number !== null && <span className="tag">p. {chunk.page_number}</span>}
            {chunk.section_title && <span className="tag">{chunk.section_title}</span>}
            <span className={chunk.has_embedding ? "tag ok" : "tag warn"}>
              {chunk.has_embedding ? "embedded" : "no vector"}
            </span>
          </header>
          <p>{chunk.text}</p>
        </article>
      ))}
    </div>
  );
}
