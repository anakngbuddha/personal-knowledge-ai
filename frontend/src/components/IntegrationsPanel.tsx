import { useEffect, useState } from "react";
import { api } from "../services/api";
import type { McpIntegration, McpIntegrationList } from "../types";

export function IntegrationsPanel() {
  const [data, setData] = useState<McpIntegrationList | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState<string | null>(null);
  const [secretDraft, setSecretDraft] = useState<Record<string, string>>({});
  const [hostDraft, setHostDraft] = useState<Record<string, string>>({});
  const [message, setMessage] = useState<string | null>(null);

  async function refresh() {
    try {
      const next = await api.listMcpIntegrations();
      setData(next);
      const hosts: Record<string, string> = {};
      for (const row of next.integrations) {
        hosts[row.server_slug] = (row.allowed_hosts || []).join(", ");
      }
      setHostDraft(hosts);
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load integrations");
    }
  }

  useEffect(() => {
    void refresh();
  }, []);

  async function save(row: McpIntegration, enabled: boolean) {
    setSaving(row.server_slug);
    setMessage(null);
    try {
      const hosts = (hostDraft[row.server_slug] || "")
        .split(",")
        .map((h) => h.trim())
        .filter(Boolean);
      const secret = secretDraft[row.server_slug]?.trim();
      await api.upsertMcpIntegration(row.server_slug, {
        enabled,
        allowed_hosts: hosts,
        secret: secret || undefined,
      });
      setSecretDraft((prev) => ({ ...prev, [row.server_slug]: "" }));
      await refresh();
      setMessage(`Saved ${row.server_slug}`);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Save failed");
    } finally {
      setSaving(null);
    }
  }

  async function ping(slug: string) {
    setSaving(slug);
    setMessage(null);
    try {
      const result = await api.testMcpIntegration(slug);
      setMessage(`${slug}: ${result.status} (${result.tools.length} tools)`);
      await refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Test failed");
    } finally {
      setSaving(null);
    }
  }

  const labels: Record<string, string> = {
    brave: "Brave Search",
    playwright: "Playwright browser",
    ms365: "Microsoft 365 / Graph",
  };
  const blurb: Record<string, string> = {
    brave: "Public web and news search. Store a Brave Search API key.",
    playwright: "Headless browser for vendor docs and public forms. Optional host allowlist.",
    ms365: "Read-only Outlook, calendar, OneDrive/SharePoint, Excel, and contacts.",
  };
  const station: Record<string, string> = {
    brave: "02.1",
    playwright: "02.2",
    ms365: "02.3",
  };

  return (
    <div className="integrations-panel">
      <div className="panel-head">
        <div>
          <p className="kicker">02 · Connectors</p>
          <h2>MCP stations</h2>
        </div>
        <span className={`stamp ${data?.mcp_enabled ? "live" : "cold"}`}>
          {data?.mcp_enabled ? "MCP live" : "MCP disabled in env"}
        </span>
      </div>
      <p className="integrations-lead">
        Wire Playwright, Microsoft 365, and Brave Search into the desk. Secrets are encrypted at rest
        and never returned. Catalog tools stay on even when MCP is cold.
      </p>
      {error && <div className="banner error">{error}</div>}
      {message && <div className="banner info">{message}</div>}
      {data && data.integrations.length === 0 && (
        <div className="empty-desk">
          <p className="kicker">Stations</p>
          <h3>No connectors on this desk.</h3>
          <p>Enable MCP in the environment, then stamp a station live.</p>
        </div>
      )}
      <div className="integration-grid">
        {(data?.integrations || []).map((row) => (
          <section key={row.server_slug} className="panel integration-card">
            <div className="panel-head">
              <div>
                <span className="playbook-index">{station[row.server_slug] || row.server_slug}</span>
                <h2>{labels[row.server_slug] || row.server_slug}</h2>
              </div>
              <span className={`stamp ${row.enabled ? "live" : "cold"}`}>
                {row.enabled ? row.status : "off"}
              </span>
            </div>
            <p className="muted">{blurb[row.server_slug]}</p>
            {row.last_error && <p className="danger-text">{row.last_error}</p>}
            <label className="field-label">
              {row.server_slug === "playwright" ? "Allowed hosts (comma-separated)" : "Secret"}
            </label>
            {row.server_slug === "playwright" ? (
              <input
                className="chat-input"
                placeholder="docs.vendor.com, learn.microsoft.com"
                value={hostDraft[row.server_slug] || ""}
                onChange={(e) =>
                  setHostDraft((prev) => ({ ...prev, [row.server_slug]: e.target.value }))
                }
              />
            ) : (
              <input
                className="chat-input"
                type="password"
                autoComplete="off"
                placeholder={row.has_secret ? "Stored — paste to rotate" : "Paste secret"}
                value={secretDraft[row.server_slug] || ""}
                onChange={(e) =>
                  setSecretDraft((prev) => ({ ...prev, [row.server_slug]: e.target.value }))
                }
              />
            )}
            {row.server_slug !== "playwright" && (
              <>
                <label className="field-label">Allowed hosts (optional)</label>
                <input
                  className="chat-input"
                  placeholder="optional host allowlist"
                  value={hostDraft[row.server_slug] || ""}
                  onChange={(e) =>
                    setHostDraft((prev) => ({ ...prev, [row.server_slug]: e.target.value }))
                  }
                />
              </>
            )}
            <div className="integration-actions">
              <button
                className="primary"
                disabled={saving === row.server_slug}
                onClick={() => void save(row, true)}
              >
                Save &amp; enable
              </button>
              <button disabled={saving === row.server_slug} onClick={() => void save(row, false)}>
                Disable
              </button>
              <button disabled={saving === row.server_slug} onClick={() => void ping(row.server_slug)}>
                Test
              </button>
            </div>
            <p className="muted">Allowlisted tools: {(row.allowed_tools || []).join(", ") || "none"}</p>
          </section>
        ))}
      </div>
    </div>
  );
}
