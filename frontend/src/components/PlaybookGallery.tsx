import { useState } from "react";

import { api } from "../services/api";
import type { Playbook, WorkflowRunSummary } from "../types";

interface Props {
  playbooks: Playbook[];
  runs: WorkflowRunSummary[];
  total: number;
  offset: number;
  pageSize: number;
  loading: boolean;
  canStart: boolean;
  authReady: boolean;
  onOpenRun: (id: string) => void;
  onStarted: (id: string) => void;
  onPage: (offset: number) => void;
  onError: (message: string | null) => void;
}

function statusClass(status: string): string {
  if (status === "succeeded") return "ready";
  if (status === "failed") return "failed";
  if (status === "waiting_approval") return "processing";
  return "uploaded";
}

export function PlaybookGallery({
  playbooks,
  runs,
  total,
  offset,
  pageSize,
  loading,
  canStart,
  authReady,
  onOpenRun,
  onStarted,
  onPage,
  onError,
}: Props) {
  const [file, setFile] = useState<File | null>(null);
  const [accountRef, setAccountRef] = useState("");
  const [starting, setStarting] = useState(false);

  const rfp = playbooks.find((p) => p.slug === "rfp-response");

  async function startRfp() {
    if (!file || !canStart) return;
    setStarting(true);
    onError(null);
    try {
      const run = await api.startRfpRun(file, accountRef.trim() || undefined);
      onStarted(run.id);
    } catch (err) {
      onError(err instanceof Error ? err.message : "failed to start RFP run");
    } finally {
      setStarting(false);
    }
  }

  return (
    <div className="workflow-gallery">
      <section className="playbook-grid">
        <article className="playbook-card">
          <header>
            <h3>{rfp?.name ?? "RFP Responder"}</h3>
            <span className="badge ready">Runnable</span>
          </header>
          <p>
            Upload a customer questionnaire (.csv or .xlsx). The engine extracts requirements, grounds
            answers in the catalog, pauses for SE review, then exports a Word deliverable.
          </p>
          <p className="playbook-meta">{rfp?.task_count ?? 6} tasks · v{rfp?.version ?? "1.0"}</p>
          <label className="file-picker">
            Spreadsheet
            <input
              type="file"
              accept=".csv,.xlsx,text/csv,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
              onChange={(e) => setFile(e.target.files?.[0] ?? null)}
              disabled={!canStart || starting}
            />
          </label>
          <label className="file-picker">
            Account ref (optional)
            <input
              type="text"
              className="search-input"
              value={accountRef}
              maxLength={128}
              placeholder="customer-account"
              onChange={(e) => setAccountRef(e.target.value)}
              disabled={!canStart || starting}
            />
          </label>
          <button className="primary" disabled={!file || !canStart || starting} onClick={() => void startRfp()}>
            {starting ? "Starting…" : "Start RFP run"}
          </button>
          {!canStart && authReady && <p className="hint">Solutions engineer role required to start a playbook.</p>}
        </article>

        <article className="playbook-card disabled">
          <header>
            <h3>Solution Composer</h3>
            <span className="badge">Phase 8</span>
          </header>
          <p>
            Discovery-to-HLD composer, BOM generator, and graph-validated bundles. Available after the
            RFP cockpit ships.
          </p>
          <button disabled>Coming soon</button>
        </article>
      </section>

      <section className="panel recent-runs">
        <div className="panel-head">
          <h2>Recent runs ({total})</h2>
        </div>
        {loading && <p className="muted">Loading…</p>}
        {!loading && runs.length === 0 && <p className="muted">No workflow runs yet.</p>}
        <ul className="run-list">
          {runs.map((run) => (
            <li key={run.id}>
              <button className="run-row" onClick={() => onOpenRun(run.id)}>
                <span className="run-slug">{run.playbook_slug}</span>
                <span className={`badge ${statusClass(run.status)}`}>{run.status.replace("_", " ")}</span>
                <span className="run-meta">
                  {run.task_counts.succeeded}/{run.task_counts.pending + run.task_counts.running + run.task_counts.waiting_approval + run.task_counts.succeeded + run.task_counts.failed} tasks
                </span>
                <span className="run-meta">{new Date(run.created_at).toLocaleString()}</span>
              </button>
            </li>
          ))}
        </ul>
        {total > pageSize && (
          <div className="pager">
            <button disabled={offset <= 0} onClick={() => onPage(Math.max(0, offset - pageSize))}>
              Previous
            </button>
            <button disabled={offset + pageSize >= total} onClick={() => onPage(offset + pageSize)}>
              Next
            </button>
          </div>
        )}
      </section>
    </div>
  );
}
