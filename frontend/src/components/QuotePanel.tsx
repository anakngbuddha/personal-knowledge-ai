import { useEffect, useState } from "react";
import { salesQuotesApi } from "../services/salesQuotes";
import type { DealSignal, PriceObservationSummary, QuoteVersion, SalesPolicy } from "../services/salesQuotes";

type DraftLine = { observation_id: string; resource_quantity: string; usage_per_resource: string; discount_percent: string; assumption: string };
const emptyLine = (): DraftLine => ({ observation_id: "", resource_quantity: "1", usage_per_resource: "1", discount_percent: "0", assumption: "" });

export function QuotePanel({ opportunityId, currency, coverageReady, canApprove = false, onSetup }: { opportunityId: string; currency: string; coverageReady: boolean; canApprove?: boolean; onSetup?: () => void }) {
  const [policies, setPolicies] = useState<SalesPolicy[]>([]);
  const [observations, setObservations] = useState<PriceObservationSummary[]>([]);
  const [versions, setVersions] = useState<QuoteVersion[]>([]);
  const [policyId, setPolicyId] = useState("");
  const [lines, setLines] = useState<DraftLine[]>([emptyLine()]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [sheetLinks, setSheetLinks] = useState<Record<string, string>>({});
  const [signals, setSignals] = useState<DealSignal[]>([]);

  useEffect(() => {
    let active = true;
    Promise.all([
      salesQuotesApi.policies(), salesQuotesApi.observations(), salesQuotesApi.quotes(opportunityId), salesQuotesApi.signals(opportunityId),
    ]).then(([policyResult, observationResult, quoteResult, signalResult]) => {
      if (!active) return;
      setPolicies(policyResult.items.filter((item) => item.currency === currency));
      setObservations(observationResult.items.filter((item) => item.observation.currency === currency));
      setVersions(quoteResult.items);
      setSignals(signalResult.items);
    }).catch((err: unknown) => {
      if (active) setError(err instanceof Error ? err.message : "Could not load quote inputs");
    });
    return () => { active = false; };
  }, [opportunityId, currency]);

  async function create(event: React.FormEvent) {
    event.preventDefault();
    if (!coverageReady || !policyId || lines.some((line) => !line.observation_id || !line.assumption.trim())) return;
    setBusy(true); setError(null);
    try {
      const next = await salesQuotesApi.create(opportunityId, policyId,
        lines.map((line) => ({ ...line, assumption: line.assumption.trim() })));
      setVersions((current) => [next, ...current]);
      setLines([emptyLine()]);
      setSignals((await salesQuotesApi.signals(opportunityId)).items);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not create quote");
    } finally { setBusy(false); }
  }

  function updateLine(index: number, patch: Partial<DraftLine>) {
    setLines((current) => current.map((line, at) => at === index ? { ...line, ...patch } : line));
  }

  async function transition(version: QuoteVersion, action: "submit" | "approve" | "issue") {
    setBusy(true); setError(null);
    try {
      const next = await salesQuotesApi.transition(version.id, action);
      setVersions((current) => current.map((item) => item.id === next.id ? next : item));
      setSignals((await salesQuotesApi.signals(opportunityId)).items);
    } catch (err) {
      setError(err instanceof Error ? err.message : `Could not ${action} quote`);
    } finally { setBusy(false); }
  }

  async function download(version: QuoteVersion) {
    setBusy(true); setError(null);
    try {
      const data = await salesQuotesApi.customerExport(version.id);
      const blob = new Blob([JSON.stringify(data, null, 2)], { type: "application/json" });
      const href = URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = href;
      link.download = `quote-${version.quote_id}-v${version.number}.json`;
      link.click();
      URL.revokeObjectURL(href);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not export quote");
    } finally { setBusy(false); }
  }

  async function exportSheet(version: QuoteVersion) {
    setBusy(true); setError(null);
    try {
      const result = await salesQuotesApi.googleSheetsExport(version.id);
      setSheetLinks((current) => ({ ...current, [version.id]: result.url }));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not export to Google Sheets");
    } finally { setBusy(false); }
  }

  return <section className="quote-panel" aria-label="Sales quotations">
    <h3>Quotation</h3>
    <p className="muted">Use approved SKU mappings, saved price observations, and a commercial policy. An administrator reviews each quote before issue.</p>
    {onSetup && <button type="button" className="battle-secondary" onClick={onSetup}>Open tenant setup</button>}
    {error && <div className="banner error" role="alert">{error}</div>}
    {!coverageReady && <p className="muted">Review all mandatory requirements before creating a new quote. Existing versions remain available below.</p>}
    {coverageReady && <form className="opportunities-form quote-form" onSubmit={create}>
      <label htmlFor="quote-policy">Commercial policy</label>
      <select id="quote-policy" value={policyId} onChange={(event) => setPolicyId(event.target.value)} required>
        <option value="">Select a policy</option>
        {policies.filter((item) => Number(item.tax_percent) === 0 && Number(item.max_discount_percent) === 0 && Number(item.min_margin_percent) === 0).map((item) => <option key={item.id} value={item.id}>{item.version} · {item.currency} · list price</option>)}
      </select>
      {lines.map((line, index) => <fieldset className="quote-line-entry" key={index}>
        <legend>Component {index + 1}</legend>
        <label htmlFor={`quote-price-${index}`}>Approved price observation</label>
        <select id={`quote-price-${index}`} value={line.observation_id} onChange={(event) => updateLine(index, { observation_id: event.target.value })} required>
          <option value="">Select a price</option>
          {observations.map((item) => <option key={item.id} value={item.id}>
            {item.observation.provider} · {item.observation.sku} · {item.observation.region} · {item.observation.unit_price ?? "tiered"} {item.observation.currency}/{item.observation.unit}
          </option>)}
        </select>
        <div className="quote-fields">
          <label htmlFor={`quote-quantity-${index}`}>Resources<input id={`quote-quantity-${index}`} type="number" min="0.0001" step="any" value={line.resource_quantity} onChange={(event) => updateLine(index, { resource_quantity: event.target.value })} required /></label>
          <label htmlFor={`quote-usage-${index}`}>Usage per resource<input id={`quote-usage-${index}`} type="number" min="0.0001" step="any" value={line.usage_per_resource} onChange={(event) => updateLine(index, { usage_per_resource: event.target.value })} required /></label>
        </div>
        <label htmlFor={`quote-assumption-${index}`}>Usage assumption</label>
        <input id={`quote-assumption-${index}`} value={line.assumption} onChange={(event) => updateLine(index, { assumption: event.target.value })} maxLength={1000} placeholder="For example, two servers for 730 hours" required />
        {lines.length > 1 && <button type="button" onClick={() => setLines((current) => current.filter((_, at) => at !== index))}>Remove component</button>}
      </fieldset>)}
      <button type="button" disabled={busy || lines.length >= 100} onClick={() => setLines((current) => [...current, emptyLine()])}>Add component</button>
      <button type="submit" disabled={busy || !policyId || lines.some((line) => !line.observation_id || !line.assumption.trim())}>Create priced draft</button>
      {(policies.length === 0 || observations.length === 0) && <p className="muted">An administrator must add a commercial policy and an approved price observation first.</p>}
    </form>}
    <div className="quote-versions">
      {signals.length > 0 && <aside aria-label="Deal follow-up"><h4>Follow-up needed</h4><ul>{signals.map((signal, index) => <li key={`${signal.kind}-${index}`}>{signal.message}</li>)}</ul></aside>}
      <h4>Quote versions</h4>
      {versions.length === 0 && <p className="muted">No quote versions yet.</p>}
      {versions.map((version) => <article key={version.id} className="quote-version">
        <div><strong>Version {version.number}</strong><span className="quote-stage">{version.status}</span></div>
        <p>{version.result.total} {version.result.currency} · {version.result.lines.length} line{version.result.lines.length === 1 ? "" : "s"}</p>
        {version.result.blockers.length > 0 && <ul>{version.result.blockers.map((blocker) => <li key={blocker}>{blocker}</li>)}</ul>}
        <div className="quote-actions">
          {version.status === "draft" && <button type="button" disabled={busy || !version.result.issueable} onClick={() => transition(version, "submit")}>Submit for approval</button>}
          {version.status === "review" && (canApprove ? <button type="button" disabled={busy} onClick={() => transition(version, "approve")}>Approve (admin)</button> : <p className="muted">A separate tenant administrator must approve this quote.</p>)}
          {version.status === "approved" && <button type="button" disabled={busy} onClick={() => transition(version, "issue")}>Issue quote</button>}
          {version.status === "issued" && <button type="button" disabled={busy} onClick={() => download(version)}>Download customer quote</button>}
          {version.status === "issued" && <button type="button" disabled={busy} onClick={() => exportSheet(version)}>Export to Google Sheets</button>}
          {sheetLinks[version.id] && <a href={sheetLinks[version.id]} target="_blank" rel="noopener noreferrer">Open spreadsheet</a>}
        </div>
      </article>)}
    </div>
  </section>;
}
