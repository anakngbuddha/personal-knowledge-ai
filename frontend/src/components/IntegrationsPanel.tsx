import { useEffect, useState } from "react";
import { api } from "../services/api";
import type { McpIntegration, McpIntegrationList } from "../types";
import {
  ZapIcon,
  CheckIcon,
  ExternalLinkIcon,
  RefreshCwIcon,
  SearchIcon,
  InfoIcon,
  ActivityIcon,
  NetworkIcon,
  DatabaseIcon,
  SparkleSquircleIcon,
} from "./Icons";
import { CustomMcpStudio } from "./CustomMcpStudio";

/* ── Per-connector metadata: label, icon, description, category ── */
const CONNECTOR_META: Record<
  string,
  {
    label: string;
    blurb: string;
    category: string;
    IconComponent: React.ComponentType<{ size?: number; className?: string }>;
  }
> = {
  brave: {
    label: "Brave Search",
    blurb: "Public web and news search powered by Brave. Add your API key to enable live web queries within grounded answers.",
    category: "Search",
    IconComponent: SearchIcon,
  },
  playwright: {
    label: "Playwright Browser",
    blurb: "Headless browser for reading vendor documentation and public web pages. Configure an optional host allowlist for security.",
    category: "Browser",
    IconComponent: NetworkIcon,
  },
  ms365: {
    label: "Microsoft 365",
    blurb: "Read-only access to Outlook mail, calendar events, OneDrive / SharePoint files, Excel workbooks, and contacts via Microsoft Graph.",
    category: "Productivity",
    IconComponent: DatabaseIcon,
  },
};

function getConnectorMeta(slug: string) {
  return CONNECTOR_META[slug] ?? {
    label: slug,
    blurb: `External connector: ${slug}`,
    category: "Custom",
    IconComponent: ZapIcon,
  };
}

export function IntegrationsPanel() {
  const [data, setData] = useState<McpIntegrationList | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState<string | null>(null);
  const [secretDraft, setSecretDraft] = useState<Record<string, string>>({});
  const [hostDraft, setHostDraft] = useState<Record<string, string>>({});
  const [message, setMessage] = useState<string | null>(null);
  const [expandedSlug, setExpandedSlug] = useState<string | null>(null);
  const [testResults, setTestResults] = useState<Record<string, { status: string; toolCount: number } | null>>({});
  const [subTab, setSubTab] = useState<"connectors" | "custom_server">("connectors");
  const [searchQuery, setSearchQuery] = useState("");
  const [category, setCategory] = useState("All");

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
      setMessage(`${enabled ? "Enabled" : "Disabled"} ${getConnectorMeta(row.server_slug).label}`);
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
      setTestResults((prev) => ({ ...prev, [slug]: { status: result.status, toolCount: result.tools.length } }));
      setMessage(`${getConnectorMeta(slug).label}: ${result.status} — ${result.tools.length} tool${result.tools.length !== 1 ? "s" : ""} available`);
      await refresh();
    } catch (err) {
      setTestResults((prev) => ({ ...prev, [slug]: null }));
      setError(err instanceof Error ? err.message : "Test failed");
    } finally {
      setSaving(null);
    }
  }

  const enabledCount = data?.integrations.filter((r) => r.enabled).length ?? 0;
  const totalCount = data?.integrations.length ?? 0;
  const filteredIntegrations = (data?.integrations || []).filter((row) => {
    const meta = getConnectorMeta(row.server_slug);
    const matchesCategory = category === "All" || meta.category === category;
    const query = searchQuery.trim().toLowerCase();
    return matchesCategory && (!query || `${meta.label} ${meta.blurb} ${meta.category}`.toLowerCase().includes(query));
  });

  return (
    <div className="connectors-workspace">
      {/* ── Top Level Navigation Switcher ── */}
      <nav className="connectors-tabs" aria-label="Connector views">
        <button
          type="button"
          onClick={() => setSubTab("connectors")}
          className={subTab === "connectors" ? "active" : ""}
          aria-pressed={subTab === "connectors"}
        >
          External Connectors <span className="connectors-tab-count">{totalCount}</span>
        </button>
        <button
          type="button"
          onClick={() => setSubTab("custom_server")}
          className={subTab === "custom_server" ? "active" : ""}
          aria-pressed={subTab === "custom_server"}
        >
          <span>Custom MCP Server</span><span className="connectors-tab-beta">BETA</span>
        </button>
      </nav>

      {subTab === "custom_server" ? (
        <CustomMcpStudio />
      ) : (
        <>
          {/* ── Hero Header ── */}
          <header className="connectors-hero">
        <div className="connectors-hero-left">
          <div className="connectors-hero-text">
            <h1 className="connectors-title">Connectors</h1>
            <p className="connectors-subtitle">
              Manage services and live tools available to your workspace. {enabledCount} of {totalCount} active.
            </p>
          </div>
        </div>
        <div className="connectors-hero-right">
          {/* Global MCP status badge */}
          <div className={`connectors-global-badge ${data?.mcp_enabled ? "live" : "cold"}`}>
            <span className={`connector-pulse-dot ${data?.mcp_enabled ? "live" : ""}`} />
            <span>{data?.mcp_enabled ? "Live Tools Active" : "Live Tools Inactive"}</span>
          </div>
          <button type="button" className="connector-add-button" onClick={() => setSubTab("custom_server")}>+ <span>Add Connector</span></button>
        </div>
      </header>

      <div className="connectors-toolbar">
        <label className="connectors-search">
          <SearchIcon size={16} />
          <span className="sr-only">Search available connectors</span>
          <input value={searchQuery} onChange={(event) => setSearchQuery(event.target.value)} placeholder="Search available connectors…" />
        </label>
        <div className="connectors-category-list" role="group" aria-label="Connector category">
          {["All", "Search", "Productivity", "Browser"].map((item) => (
            <button key={item} type="button" className={category === item ? "active" : ""} aria-pressed={category === item} onClick={() => setCategory(item)}>
              {item === "All" ? `All (${totalCount})` : item}
            </button>
          ))}
        </div>
      </div>


      {/* ── Alerts ── */}
      {error && (
        <div className="connectors-alert error" role="alert">
          <span className="connectors-alert-icon">⚠</span>
          <span>{error}</span>
          <button type="button" className="connectors-alert-dismiss" onClick={() => setError(null)}>×</button>
        </div>
      )}
      {message && (
        <div className="connectors-alert success" role="status">
          <CheckIcon size={14} />
          <span>{message}</span>
          <button type="button" className="connectors-alert-dismiss" onClick={() => setMessage(null)}>×</button>
        </div>
      )}

      {/* ── Empty State ── */}
      {data && data.integrations.length === 0 && (
        <div className="connectors-empty">
          <div className="connectors-empty-icon">
            <SparkleSquircleIcon size={56} />
          </div>
          <h3 className="connectors-empty-title">No Connectors Registered</h3>
          <p className="connectors-empty-desc">
            Ask an administrator to configure web search, browser access, or Microsoft 365 integration to extend the intelligence engine.
          </p>
        </div>
      )}

      {/* ── Connector Catalog ── */}
      <div className="connectors-grid">
        {filteredIntegrations.map((row) => {
          const meta = getConnectorMeta(row.server_slug);
          const isExpanded = expandedSlug === row.server_slug;
          const isSaving = saving === row.server_slug;
          const test = testResults[row.server_slug];
          const IconComponent = meta.IconComponent;

          return (
            <article
              key={row.server_slug}
              className={`connector-card ${row.enabled ? "enabled" : "disabled"} ${isExpanded ? "expanded" : ""}`}
            >
              {/* Card Header */}
              <button type="button" className="connector-card-header" aria-expanded={isExpanded} aria-label={`${meta.label} settings`} onClick={() => setExpandedSlug(isExpanded ? null : row.server_slug)}>
                <div className="connector-card-icon-squircle">
                  <IconComponent size={20} />
                </div>
                <div className="connector-card-titles">
                  <div className="connector-card-name-row">
                    <h3 className="connector-card-name">{meta.label}</h3>
                  </div>
                  <span className="connector-card-category">{meta.category}</span>
                </div>
                <div className="connector-card-status-area">
                  <span className={`connector-status-pill ${row.enabled ? "enabled" : "disabled"}`}>
                    <span className={`connector-status-dot ${row.enabled ? (row.status === "healthy" || row.status === "ok" ? "healthy" : "warn") : "off"}`} />
                    {row.enabled ? row.status : "off"}
                  </span>
                  <span className={`connector-expand-chevron ${isExpanded ? "open" : ""}`}>
                    <svg width="12" height="12" viewBox="0 0 12 12" fill="none" xmlns="http://www.w3.org/2000/svg">
                      <path d="M3 4.5L6 7.5L9 4.5" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
                    </svg>
                  </span>
                </div>
              </button>

              {/* Card Description */}
              <p className="connector-card-blurb">{meta.blurb}</p>

              {/* Last Error Banner */}
              {row.last_error && (
                <div className="connector-error-banner">
                  <InfoIcon size={13} />
                  <span>{row.last_error}</span>
                </div>
              )}

              {/* Allowed Tools Summary */}
              {isExpanded && row.allowed_tools && row.allowed_tools.length > 0 && (
                <div className="connector-tools-row">
                  <span className="connector-tools-label">Tools:</span>
                  <div className="connector-tools-chips">
                    {row.allowed_tools.map((tool) => (
                      <span key={tool} className="connector-tool-chip">{tool}</span>
                    ))}
                  </div>
                </div>
              )}

              {/* Test Result Inline */}
              {test && (
                <div className="connector-test-result">
                  <ActivityIcon size={13} />
                  <span>{test.status} — {test.toolCount} tool{test.toolCount !== 1 ? "s" : ""}</span>
                </div>
              )}

              {/* Expandable Configuration Form */}
              <div className={`connector-config-panel ${isExpanded ? "open" : ""}`}>
                <div className="connector-config-inner">
                  <div className="connector-config-divider" />

                  {/* Secret / Host Configuration */}
                  {row.server_slug === "playwright" ? (
                    <div className="connector-field-group">
                      <label className="connector-field-label">
                        <NetworkIcon size={13} />
                        <span>Allowed Hosts</span>
                      </label>
                      <input
                        className="connector-field-input"
                        placeholder="docs.vendor.com, learn.microsoft.com"
                        value={hostDraft[row.server_slug] || ""}
                        onChange={(e) =>
                          setHostDraft((prev) => ({ ...prev, [row.server_slug]: e.target.value }))
                        }
                      />
                      <span className="connector-field-hint">Comma-separated hostnames the browser is allowed to visit</span>
                    </div>
                  ) : (
                    <>
                      <div className="connector-field-group">
                        <label className="connector-field-label">
                          <ZapIcon size={13} />
                          <span>Secret / API Key</span>
                        </label>
                        <input
                          className="connector-field-input"
                          type="password"
                          autoComplete="off"
                          placeholder={row.has_secret ? "Stored securely — paste to rotate" : "Paste your API key or secret"}
                          value={secretDraft[row.server_slug] || ""}
                          onChange={(e) =>
                            setSecretDraft((prev) => ({ ...prev, [row.server_slug]: e.target.value }))
                          }
                        />
                        {row.has_secret && (
                          <span className="connector-field-hint secure">
                            <CheckIcon size={11} /> Secret stored — never displayed
                          </span>
                        )}
                      </div>
                      <div className="connector-field-group">
                        <label className="connector-field-label">
                          <NetworkIcon size={13} />
                          <span>Allowed Hosts (optional)</span>
                        </label>
                        <input
                          className="connector-field-input"
                          placeholder="Optional host allowlist"
                          value={hostDraft[row.server_slug] || ""}
                          onChange={(e) =>
                            setHostDraft((prev) => ({ ...prev, [row.server_slug]: e.target.value }))
                          }
                        />
                      </div>
                    </>
                  )}

                  {/* Actions */}
                  <div className="connector-actions-bar">
                    <button
                      type="button"
                      className="connector-action-btn primary"
                      disabled={isSaving}
                      onClick={() => void save(row, true)}
                    >
                      {isSaving ? (
                        <RefreshCwIcon size={13} className="connector-spinner" />
                      ) : (
                        <CheckIcon size={13} />
                      )}
                      <span>{isSaving ? "Saving…" : "Save & Enable"}</span>
                    </button>
                    <button
                      type="button"
                      className="connector-action-btn secondary"
                      disabled={isSaving}
                      onClick={() => void save(row, false)}
                    >
                      <span>Disable</span>
                    </button>
                    <button
                      type="button"
                      className="connector-action-btn test"
                      disabled={isSaving}
                      onClick={() => void ping(row.server_slug)}
                      title="Test connection and list available tools"
                    >
                      <ActivityIcon size={13} />
                      <span>Test</span>
                    </button>
                  </div>
                </div>
              </div>
            </article>
          );
        })}
        {data && filteredIntegrations.length === 0 && data.integrations.length > 0 && (
          <div className="connectors-no-results">No connectors match your search. <button type="button" onClick={() => { setSearchQuery(""); setCategory("All"); }}>Clear filters</button></div>
        )}
        <button type="button" className="connector-create-card" onClick={() => setSubTab("custom_server")}>
          <span className="connector-create-plus">+</span>
          <strong>Add or build a custom connector</strong>
          <span>Connect an internal MCP endpoint to your workspace.</span>
          <span className="connector-create-link">Open MCP studio →</span>
        </button>
      </div>

      {/* ── Bottom Security Note ── */}
      <div className="connectors-security-footer">
        <InfoIcon size={14} />
        <p>
          Secrets are encrypted at rest and never returned to the browser. Product answers continue working when connectors are disabled.
        </p>
      </div>
        </>
      )}
    </div>
  );
}
