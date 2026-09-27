import { useEffect, useState } from "react";
import { OpsPanel } from "./OpsPanel";
import { api } from "../services/api";
import type { PrincipalProfile } from "../types";
import { ActivityIcon, CheckIcon, DatabaseIcon, LogOutIcon, SettingsIcon, SunIcon, MoonIcon } from "./Icons";

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
        <p>Manage workspace identity, appearance, session access, and system health.</p>
      </header>
      <div className="settings-layout">
        <div className="settings-primary">
          <section className="settings-section settings-card" aria-labelledby="workspace-settings-title">
            <div className="settings-card-heading"><span className="settings-icon"><SettingsIcon size={18} /></span><div><h2 id="workspace-settings-title">Workspace profile</h2><p>Identity and permissions for your current workspace.</p></div></div>
            <div className="settings-profile-grid">
              <div className="settings-data-field"><span>Workspace name</span><strong>{principal?.organization_name || "Personal workspace"}</strong></div>
              <div className="settings-data-field"><span>Your role</span><strong>{principal?.role || "Member"}</strong></div>
            </div>
            <div className="settings-role-note"><CheckIcon size={15} /><span>{admin ? "You have workspace administration access." : "Your access is managed by a workspace administrator."}</span></div>
          </section>
          <section className="settings-section settings-card" aria-labelledby="appearance-settings-title">
            <div className="settings-card-heading"><span className="settings-icon"><SunIcon size={18} /></span><div><h2 id="appearance-settings-title">Appearance</h2><p>Choose the canvas that works best for you.</p></div></div>
            <div className="settings-theme-options" role="group" aria-label="Color theme">
              <button type="button" className={`settings-theme-choice light ${theme === "light" ? "active" : ""}`} aria-pressed={theme === "light"} onClick={() => onThemeChange("light")}>
                <span className="settings-theme-preview"><i /><i /><i /></span><span className="settings-theme-caption"><SunIcon size={15} /> Light {theme === "light" && <CheckIcon size={15} />}</span>
              </button>
              <button type="button" className={`settings-theme-choice dark ${theme === "dark" ? "active" : ""}`} aria-pressed={theme === "dark"} onClick={() => onThemeChange("dark")}>
                <span className="settings-theme-preview"><i /><i /><i /></span><span className="settings-theme-caption"><MoonIcon size={15} /> Dark {theme === "dark" && <CheckIcon size={15} />}</span>
              </button>
            </div>
            <p className="settings-help">This preference is saved on this browser.</p>
          </section>
          <section className="settings-section settings-card" aria-labelledby="session-settings-title">
            <div className="settings-card-heading"><span className="settings-icon"><LogOutIcon size={18} /></span><div><h2 id="session-settings-title">Session</h2><p>Manage access on this device.</p></div></div>
            <div className="settings-session-row"><div><strong>Current browser</strong><p>You are signed in to Deep Atlas on this browser.</p></div><button type="button" className="settings-signout" onClick={onSignOut}>Sign out</button></div>
          </section>
        </div>
        <aside className="settings-secondary">
          {admin && <section className="settings-card settings-health-card" aria-labelledby="health-settings-title">
            <div className="settings-card-heading"><span className="settings-icon"><ActivityIcon size={18} /></span><div><h2 id="health-settings-title">System health</h2><p>Live service checks</p></div></div>
            {statusError && <p className="settings-health-error" role="alert">{statusError}</p>}
            {rows.length === 0 && !statusError && <p className="settings-help">Checking services…</p>}
            <div className="settings-health-list">{rows.map((row) => <div className="settings-health-row" key={row.label}><span><i className={row.ok ? "healthy" : "unhealthy"} />{row.label}</span><strong className={row.ok ? "healthy" : "unhealthy"}>{labelStatus(row.ok)}</strong><small>{row.detail}</small></div>)}</div>
            {queueDetail && <p className="settings-health-queue">{queueDetail}</p>}
          </section>}
          {admin && <section className="settings-card settings-admin-card"><div className="settings-card-heading"><span className="settings-icon"><DatabaseIcon size={18} /></span><div><h2>Administration</h2><p>Advanced workspace operations</p></div></div><details className="settings-details" onToggle={(event) => setShowAdvanced(event.currentTarget.open)}><summary>Open administration tools</summary>{showAdvanced && <OpsPanel mode="admin" />}</details></section>}
          {!admin && <section className="settings-card settings-admin-card"><h2>Need help?</h2><p>Contact a workspace administrator to change access or configuration.</p></section>}
        </aside>
      </div>
    </div>
  );
}
