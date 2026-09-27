import { useEffect, useState } from "react";
import { OpsPanel } from "./OpsPanel";
import { api } from "../services/api";
import type { PrincipalProfile } from "../types";

interface Props {
  principal: PrincipalProfile | null;
  onSignOut: () => void;
  theme: "light" | "dark";
  onThemeChange: (theme: "light" | "dark") => void;
}

interface SystemRow {
  label: string;
  ok: boolean;
  detail: string;
}

function labelStatus(ok: boolean): string {
  return ok ? "OK" : "Needs attention";
}

export function SettingsPanel({ principal, onSignOut, theme, onThemeChange }: Props) {
  const admin = Boolean(principal?.is_admin || principal?.is_owner);
  const [rows, setRows] = useState<SystemRow[]>([]);
  const [queueDetail, setQueueDetail] = useState<string | null>(null);
  const [statusError, setStatusError] = useState<string | null>(null);
  const [showAdvanced, setShowAdvanced] = useState(false);

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
      <header className="settings-heading">
        <h1>Settings</h1>
        <p>Manage your workspace and display preferences.</p>
      </header>
      <section className="settings-section" aria-labelledby="workspace-settings-title">
        <h2 id="workspace-settings-title">Workspace</h2>
        <div className="settings-row"><span>Name</span><strong>{principal?.organization_name || "Personal workspace"}</strong></div>
        <div className="settings-row"><span>Your role</span><strong>{principal?.role || "Member"}</strong></div>
      </section>
      <section className="settings-section" aria-labelledby="appearance-settings-title">
        <h2 id="appearance-settings-title">Appearance</h2>
        <div className="settings-row">
          <div><strong>Color theme</strong><p>Choose how Deep Atlas looks on this browser.</p></div>
          <div className="settings-segmented" role="group" aria-label="Color theme">
            <button type="button" className={theme === "light" ? "active" : ""} aria-pressed={theme === "light"} onClick={() => onThemeChange("light")}>Light</button>
            <button type="button" className={theme === "dark" ? "active" : ""} aria-pressed={theme === "dark"} onClick={() => onThemeChange("dark")}>Dark</button>
          </div>
        </div>
      </section>
      <section className="settings-section" aria-labelledby="session-settings-title">
        <h2 id="session-settings-title">Session</h2>
        <div className="settings-row">
          <div><strong>Signed in on this browser</strong><p>Sign out when you finish using a shared device.</p></div>
          <button type="button" className="settings-signout" onClick={onSignOut}>Sign out</button>
        </div>
      </section>
      {admin && (
        <section className="settings-section">
          <h2>Administration</h2>
          <details className="settings-details">
            <summary>System status</summary>
          <div className="system-status">
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
          </details>
          <details className="settings-details" onToggle={(event) => setShowAdvanced(event.currentTarget.open)}>
            <summary>Advanced administration</summary>
            {showAdvanced && <OpsPanel mode="admin" />}
          </details>
        </section>
      )}
    </div>
  );
}
