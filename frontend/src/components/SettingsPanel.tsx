import { useEffect, useState } from "react";
import { OpsPanel } from "./OpsPanel";
import { api } from "../services/api";
import type { PrincipalProfile } from "../types";

interface Props {
  principal: PrincipalProfile | null;
  onSignOut: () => void;
}

interface SystemRow {
  label: string;
  ok: boolean;
  detail: string;
}

function labelStatus(ok: boolean): string {
  return ok ? "OK" : "Needs attention";
}

export function SettingsPanel({ principal, onSignOut }: Props) {
  const admin = Boolean(principal?.is_admin || principal?.is_owner);
  const [rows, setRows] = useState<SystemRow[]>([]);
  const [queueDetail, setQueueDetail] = useState<string | null>(null);
  const [statusError, setStatusError] = useState<string | null>(null);

  useEffect(() => {
    if (!admin) return;
    let cancelled = false;
    const load = async () => {
      try {
        const data = await api.healthDependencies();
        if (cancelled) return;
        const c = data.checks;
        const counts = (c.ingestion_queue?.counts || {}) as Record<string, number>;
        const queued = Number(counts.queued || 0);
        const running = Number(counts.running || 0);
        const aiWaiting = Number(c.gemini?.queued || 0);
        const next: SystemRow[] = [
          {
            label: "Database",
            ok: Boolean(c.postgres?.ok),
            detail: c.postgres?.ok ? "Connected" : String(c.postgres?.error || "Unavailable"),
          },
          {
            label: "File storage",
            ok: Boolean(c.storage?.ok),
            detail: c.storage?.ok
              ? String(c.storage.backend || "Connected")
              : String(c.storage?.error || "Unavailable"),
          },
          {
            label: "AI key",
            ok: Boolean(c.llm?.ok ?? c.llm?.key_configured),
            detail: c.llm?.key_configured
              ? `Ready (${String(c.llm.provider || "ai")})`
              : "Not configured",
          },
          {
            label: "OCR",
            ok: Boolean(c.ocr?.ok),
            detail: c.ocr?.ok
              ? String(c.ocr.provider || "Ready")
              : String(c.ocr?.error || "Unavailable"),
          },
          {
            label: "Background jobs",
            ok: Boolean(c.ingestion_queue?.ok),
            detail: c.ingestion_queue?.worker_in_process
              ? `${running} reading, ${queued} waiting`
              : "Worker is off",
          },
        ];
        setRows(next);
        setQueueDetail(
          aiWaiting === 0 ? "AI wait queue is clear" : `AI wait queue: ${aiWaiting} waiting`,
        );
        setStatusError(null);
      } catch {
        if (!cancelled) setStatusError("Could not load system status.");
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

          <div className="system-status">
            <h3>System status</h3>
            {statusError && <p className="muted">{statusError}</p>}
            {rows.length > 0 && (
              <table className="status-table">
                <thead>
                  <tr>
                    <th>Check</th>
                    <th>Status</th>
                    <th>Detail</th>
                  </tr>
                </thead>
                <tbody>
                  {rows.map((row) => (
                    <tr key={row.label}>
                      <td>{row.label}</td>
                      <td>
                        <span className={row.ok ? "status-ok" : "status-bad"}>
                          {labelStatus(row.ok)}
                        </span>
                      </td>
                      <td>{row.detail}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
            {queueDetail && <p className="muted queue-note">{queueDetail}</p>}
          </div>

          <OpsPanel mode="admin" />
        </section>
      )}
    </div>
  );
}
