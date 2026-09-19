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

  if (!documentId) return <p className="muted">Select a document to inspect its chunks.</p>;
  if (loading) return <p className="muted">Loading chunks...</p>;
  if (error) return <p className="error">{error}</p>;
  if (chunks.length === 0) return <p className="muted">No chunks yet. Ingestion may still be running.</p>;

  return (
    <div className="chunks">
      {chunks.map((chunk) => (
        <article key={chunk.id} className="chunk">
          <header>
            <span className="chunk-index">#{chunk.chunk_index}</span>
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
