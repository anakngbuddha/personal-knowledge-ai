import { useEffect, useState } from "react";
import { api } from "../services/api";
import type { FreshnessAlert, RestoreDrill, SsoStatus, VendorSource } from "../types";

export function OpsPanel({ mode = "all" }: { mode?: "watches" | "admin" | "all" }) {
  const [sources, setSources] = useState<VendorSource[]>([]);
  const [alerts, setAlerts] = useState<FreshnessAlert[]>([]);
  const [drills, setDrills] = useState<RestoreDrill[]>([]);
  const [sso, setSso] = useState<SsoStatus | null>(null);
  const [label, setLabel] = useState("");
  const [url, setUrl] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function refresh() {
    try {
      const [src, alertList, drillList, status] = await Promise.all([
        api.listVendorSources(),
        api.listFreshnessAlerts(),
        api.listRestoreDrills().catch(() => ({ drills: [] as RestoreDrill[], total: 0, limit: 20, offset: 0 })),
        api.ssoStatus(),
      ]);
      setSources(src.sources);
      setAlerts(alertList.alerts);
      setDrills(drillList.drills);
      setSso(status);
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load watch desk");
    }
  }

  useEffect(() => {
    void refresh();
  }, []);

  async function addSource() {
    setBusy(true);
    setMessage(null);
    try {
      await api.createVendorSource({ label, url });
      setLabel("");
      setUrl("");
      setMessage("Source registered. The poller will hash it on the next pass.");
      await refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not add source");
    } finally {
      setBusy(false);
    }
  }

  async function check(id: string) {
    setBusy(true);
    try {
      const result = await api.checkVendorSource(id);
      setMessage(
        result.status === "queued"
          ? "Crawl queued. Pages will be indexed in the background."
          : result.changed
            ? "Upstream changed — staleness alert raised."
            : result.error
              ? result.error
              : `Still ${result.status}.`,
      );
      await refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Check failed");
    } finally {
      setBusy(false);
    }
  }

  async function ack(id: string) {
    try {
      await api.ackFreshnessAlert(id);
      await refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Ack failed");
    }
  }

  async function drill() {
    setBusy(true);
    try {
      const result = await api.runRestoreDrill();
      setMessage(
        result.within_sla
          ? `Restore drill ${result.status} in ${result.duration_seconds?.toFixed(2)}s — within SLA.`
          : `Restore drill ${result.status}: ${result.error_message || "outside SLA"}`,
      );
      await refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Drill failed");
    } finally {
      setBusy(false);
    }
  }

  const showWatches = mode !== "admin";
  const showAdmin = mode !== "watches";

  return (
    <div className="ops-desk">
      {error && <div className="banner error">{error}</div>}
      {message && <div className="banner info">{message}</div>}

      {showWatches && (
      <section className="panel">
        <div className="panel-head">
          <div>
            <h2>Watch a web page</h2>
          </div>
        </div>
        <p className="muted">
          Register a public URL. The crawler indexes same-origin pages and raises an alert when one
          of them changes.
        </p>
        <div className="ops-form">
          <input
            className="chat-input"
            placeholder="Cisco ASA datasheet"
            value={label}
            onChange={(e) => setLabel(e.target.value)}
          />
          <input
            className="chat-input"
            placeholder="https://vendor.example/datasheet.pdf"
            value={url}
            onChange={(e) => setUrl(e.target.value)}
          />
          <button type="button" className="primary" disabled={busy || !label.trim() || !url.trim()} onClick={() => void addSource()}>
            Watch URL
          </button>
        </div>
        {sources.length === 0 ? (
          <p className="empty-copy">Nothing on the watch list. Add a public datasheet URL to start hashing.</p>
        ) : (
          <ul className="ops-list">
            {sources.map((row) => (
              <li key={row.id}>
                <div>
                  <strong>{row.label}</strong>
                  <span className={`stamp ${row.status === "stale" ? "stale" : "fresh"}`}>{row.status}</span>
                  <p className="muted">{row.url}</p>
                </div>
                <button type="button" disabled={busy} onClick={() => void check(row.id)}>
                  Check now
                </button>
              </li>
            ))}
          </ul>
        )}
      </section>
      )}

      {showWatches && (
      <section className="panel">
        <div className="panel-head">
          <div>
            <h2>Sources that may be out of date</h2>
          </div>
        </div>
        {alerts.length === 0 ? (
          <p className="empty-copy">No open staleness alerts. Upstream hashes match the last known copy.</p>
        ) : (
          <ul className="ops-list">
            {alerts.map((alert) => (
              <li key={alert.id}>
                <div>
                  <span className="stamp stale">{alert.kind}</span>
                  {alert.pages && alert.pages.length > 0 ? (
                    alert.pages.map((page) => (
                      <p key={`${alert.id}-${page.url}`} className="muted">
                        {page.change}: {page.url}
                      </p>
                    ))
                  ) : (
                    <p className="muted">
                      {alert.previous_hash?.slice(0, 10)} → {alert.new_hash?.slice(0, 10)}
                    </p>
                  )}
                </div>
                <button type="button" onClick={() => void ack(alert.id)}>
                  Acknowledge
                </button>
              </li>
            ))}
          </ul>
        )}
      </section>
      )}

      {showAdmin && (
      <div className="layout">
        <section className="panel">
          <div className="panel-head">
            <div>
              <p className="kicker">Recovery</p>
              <h2>Restore drills</h2>
            </div>
            <button type="button" className="primary" disabled={busy} onClick={() => void drill()}>
              Run drill
            </button>
          </div>
          <p className="muted">Logical dump → scratch restore → row-count compare, timed against SLA.</p>
          {drills.length === 0 ? (
            <p className="empty-copy">No drills recorded. Admins can prove restore within SLA from this desk.</p>
          ) : (
            <ul className="ops-list">
              {drills.map((row) => (
                <li key={row.id}>
                  <div>
                    <span className={`stamp ${row.within_sla ? "fresh" : "stale"}`}>{row.status}</span>
                    <p className="muted">
                      {row.duration_seconds?.toFixed(2)}s / {row.sla_seconds}s SLA
                    </p>
                  </div>
                </li>
              ))}
            </ul>
          )}
        </section>
        <section className="panel">
          <div className="panel-head">
            <div>
              <p className="kicker">Identity</p>
              <h2>SSO</h2>
            </div>
            <span className={`stamp ${sso?.sso_enabled ? "fresh" : "stale"}`}>
              {sso?.sso_enabled ? "armed" : "local JWT"}
            </span>
          </div>
          <p className="muted">Sign-in with your company identity, when an administrator has turned it on.</p>
          <dl className="ops-dl">
            <dt>OIDC</dt>
            <dd>{sso?.oidc_configured ? sso.oidc_issuer || "configured" : "not configured"}</dd>
            <dt>SAML</dt>
            <dd>{sso?.saml_configured ? sso.saml_issuer || "configured" : "not configured"}</dd>
          </dl>
        </section>
      </div>
      )}
    </div>
  );
}
