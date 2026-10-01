import { useCallback, useEffect, useRef, useState } from "react";

import { api } from "../services/api";
import { getAccessToken } from "../services/http";
import { pageCursor } from "../services/pagination";
import type { KnowledgeDocument } from "../types";

const POLL_INTERVAL_MS = 2500;

export function useDocuments(active = true) {
  const [documents, setDocuments] = useState<KnowledgeDocument[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [page, setPage] = useState(0);
  const [hasMore, setHasMore] = useState(false);
  const cursors = useRef<string[]>([""]);
  const timer = useRef<number | null>(null);

  const refresh = useCallback(async () => {
    if (!active || !getAccessToken()) {
      setLoading(false);
      return;
    }
    try {
      const rows = await api.listDocuments({ limit: 100, cursor: cursors.current[page] });
      if (rows.length) cursors.current[page + 1] = pageCursor(rows[rows.length - 1].uploaded_at ?? "1970-01-01T00:00:00Z", rows[rows.length - 1].id);
      setDocuments(rows);
      setHasMore(rows.length === 100);
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "could not reach the API");
    } finally {
      setLoading(false);
    }
  }, [active, page]);

  useEffect(() => { cursors.current = [""]; setPage(0); setDocuments([]); }, [active]);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  // Poll only while something is still being ingested.
  useEffect(() => {
    const busy = documents.some((d) => d.status === "processing" || d.status === "uploaded");
    if (!busy) {
      if (timer.current) window.clearInterval(timer.current);
      timer.current = null;
      return;
    }
    if (timer.current) return;
    timer.current = window.setInterval(() => void refresh(), POLL_INTERVAL_MS);
    return () => {
      if (timer.current) window.clearInterval(timer.current);
      timer.current = null;
    };
  }, [documents, refresh]);

  return { documents, error, loading, refresh, setError, page, setPage, hasMore };
}
