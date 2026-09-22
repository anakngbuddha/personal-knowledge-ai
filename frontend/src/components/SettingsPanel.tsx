import { useEffect, useState } from "react";
import { OpsPanel } from "./OpsPanel";
import { api } from "../services/api";
import type { PrincipalProfile } from "../types";

interface Props {
  principal: PrincipalProfile | null;
  onSignOut: () => void;
}

interface QueueSnapshot {
  aiWaiting: number;
  filesQueued: number;
  filesRunning: number;
  workerOn: boolean;
}

export function SettingsPanel({ principal, onSignOut }: Props) {
  const admin = Boolean(principal?.is_admin || principal?.is_owner);
  const [queue, setQueue] = useState<QueueSnapshot | null>(null);
  const [queueError, setQueueError] = useState<string | null>(null);

  useEffect(() => {
    if (!admin) return;
    let cancelled = false;
    const load = async () => {
      try {
        const data = await api.healthDependencies();
        if (cancelled) return;
        const gemini = data.checks.gemini || {};
        const ingestion = data.checks.ingestion_queue || {};
        const counts = (ingestion.counts || {}) as Record<string, number>;
        setQueue({
          aiWaiting: Number(gemini.queued || 0),
          filesQueued: Number(counts.queued || counts.QUEUED || 0),
          filesRunning: Number(counts.running || counts.RUNNING || 0),
          workerOn: Boolean(ingestion.worker_in_process),
        });
        setQueueError(null);
      } catch {
        if (!cancelled) setQueueError("Could not load queue status.");
      }
    };
    void load();
    const timer = window.setInterval(() => void load(), 15000);
    return () => {
      cancelled = true;
      window.clearInterval(timer);
    };
  }, [admin]);

  return (
    <div className="settings-desk">
      <section className="panel">
        <div className="panel-head">
          <div>
            <h2>Settings</h2>
          </div>
          <button type="button" className="link-button" onClick={onSignOut}>
            Sign out
          </button>
        </div>
        <p className="muted">Your session stays on this browser until you sign out.</p>
      </section>
      {admin && (
        <section className="panel">
          <div className="panel-head">
            <div>
              <h2>Admin</h2>
            </div>
          </div>
          <dl className="ops-dl">
            <dt>Workspace</dt>
            <dd>{principal?.organization_name || "This workspace"}</dd>
            <dt>Role</dt>
            <dd>{principal?.role || "member"}</dd>
          </dl>
          <div className="queue-status">
            <h3>Queue status</h3>
            {queueError && <p className="muted">{queueError}</p>}
            {queue && (
              <dl className="ops-dl">
                <dt>AI wait queue</dt>
                <dd>{queue.aiWaiting === 0 ? "Clear" : `${queue.aiWaiting} waiting`}</dd>
                <dt>File reading</dt>
                <dd>
                  {queue.filesRunning} running, {queue.filesQueued} waiting
                  {queue.workerOn ? "" : " (background worker off)"}
                </dd>
              </dl>
            )}
          </div>
          <OpsPanel mode="admin" />
        </section>
      )}
    </div>
  );
}
