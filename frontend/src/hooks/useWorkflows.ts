import { useCallback, useEffect, useRef, useState } from "react";

import { api } from "../services/api";
import type { Playbook, PrincipalProfile, WorkflowRun, WorkflowRunSummary } from "../types";

const POLL_INTERVAL_MS = 2000;
const RUNS_PAGE_SIZE = 20;

export function usePrincipal(active = true) {
  const [principal, setPrincipal] = useState<PrincipalProfile | null>(null);

  useEffect(() => {
    if (!active) {
      setPrincipal(null);
      return;
    }
    let cancelled = false;
    void api
      .me()
      .then((profile) => {
        if (!cancelled) setPrincipal(profile);
      })
      .catch(() => {
        if (!cancelled) setPrincipal(null);
      });
    return () => {
      cancelled = true;
    };
  }, [active]);

  return principal;
}

export function usePlaybookGallery() {
  const [playbooks, setPlaybooks] = useState<Playbook[]>([]);
  const [runs, setRuns] = useState<WorkflowRunSummary[]>([]);
  const [total, setTotal] = useState(0);
  const [offset, setOffset] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(async (nextOffset = offset) => {
    try {
      const [catalog, listed] = await Promise.all([
        api.listPlaybooks(),
        api.listWorkflowRuns(RUNS_PAGE_SIZE, nextOffset),
      ]);
      setPlaybooks(catalog.playbooks);
      setRuns(listed.runs);
      setTotal(listed.total);
      setOffset(listed.offset);
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "could not load workflows");
    } finally {
      setLoading(false);
    }
  }, [offset]);

  useEffect(() => {
    void refresh(0);
  }, []);

  return { playbooks, runs, total, offset, pageSize: RUNS_PAGE_SIZE, loading, error, setError, refresh };
}

export function useWorkflowRun(runId: string | null) {
  const [run, setRun] = useState<WorkflowRun | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const timer = useRef<number | null>(null);

  const refresh = useCallback(async () => {
    if (!runId) return;
    try {
      const next = await api.getWorkflowRun(runId);
      setRun(next);
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "could not load run");
    } finally {
      setLoading(false);
    }
  }, [runId]);

  useEffect(() => {
    if (!runId) {
      setRun(null);
      setError(null);
      setLoading(false);
      return;
    }
    setLoading(true);
    void refresh();
  }, [runId, refresh]);

  useEffect(() => {
    const busy = run?.status === "pending" || run?.status === "running";
    if (!runId || !busy) {
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
  }, [runId, run?.status, refresh]);

  return { run, setRun, error, setError, loading, refresh };
}
