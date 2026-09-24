import { useCallback, useEffect, useRef, useState } from "react";

import { api } from "../services/api";
import { getAccessToken } from "../services/http";
import type { KnowledgeDocument } from "../types";

const POLL_INTERVAL_MS = 2500;

export function useDocuments(active = true) {
  const [documents, setDocuments] = useState<KnowledgeDocument[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const timer = useRef<number | null>(null);

  const refresh = useCallback(async () => {
    if (!active || !getAccessToken()) {
      setLoading(false);
      return;
    }
    try {
      setDocuments(await api.listDocuments());
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "could not reach the API");
    } finally {
      setLoading(false);
    }
  }, [active]);

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

  return { documents, error, loading, refresh, setError };
}
