import { useEffect, useState } from "react";
import { opportunityApi } from "../services/opportunities";
import type { Coverage, Opportunity, Requirement } from "../services/opportunities";
import { QuotePanel } from "./QuotePanel";
import { ClaimsPanel } from "./ClaimsPanel";
import "../styles/opportunities.css";

const coverageStates: Requirement["coverage_state"][] = [
  "unreviewed", "covered", "partial", "gap", "excluded",
];

export function OpportunitiesWorkspace() {
  const [items, setItems] = useState<Opportunity[]>([]);
  const [selected, setSelected] = useState<string | null>(null);
  const [coverage, setCoverage] = useState<Coverage | null>(null);
  const [offset, setOffset] = useState(0);
  const [title, setTitle] = useState("");
  const [currency, setCurrency] = useState("USD");
  const [requirementText, setRequirementText] = useState("");
  const [rfpText, setRfpText] = useState("");
  const [reviewDrafts, setReviewDrafts] = useState<Record<string, { state: Requirement["coverage_state"]; note: string }>>({});
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    let active = true;
    opportunityApi.list().then((result) => {
      if (active) setItems(result.items);
    }).catch((err: unknown) => {
      if (active) setError(err instanceof Error ? err.message : "Could not load opportunities");
    });
    return () => { active = false; };
  }, []);

  useEffect(() => {
    if (!selected) { setCoverage(null); return; }
    let active = true;
    opportunityApi.coverage(selected, offset).then((result) => {
      if (active) setCoverage(result);
    }).catch((err: unknown) => {
      if (active) setError(err instanceof Error ? err.message : "Could not load coverage");
    });
    return () => { active = false; };
  }, [selected, offset]);

  async function reloadCoverage(id: string) {
    setCoverage(await opportunityApi.coverage(id, offset));
  }

  async function createOpportunity(event: React.FormEvent) {
    event.preventDefault();
    if (!title.trim()) return;
    setBusy(true); setError(null);
    try {
      const created = await opportunityApi.create(title.trim(), currency);
      setItems((current) => [created, ...current]);
      setTitle(""); setSelected(created.id); setOffset(0);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not create opportunity");
    } finally { setBusy(false); }
  }

  async function addRequirement(event: React.FormEvent) {
    event.preventDefault();
    if (!selected || !requirementText.trim()) return;
    setBusy(true); setError(null);
    try {
      await opportunityApi.addRequirement(selected, requirementText.trim(), "must");
      setRequirementText(""); await reloadCoverage(selected);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not add requirement");
    } finally { setBusy(false); }
  }

  async function importRequirements(event: React.FormEvent) {
    event.preventDefault();
    if (!selected || !rfpText.trim()) return;
    setBusy(true); setError(null);
    try {
      await opportunityApi.importRequirements(selected, rfpText);
      setRfpText(""); setOffset(0);
      setCoverage(await opportunityApi.coverage(selected));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not import requirements");
    } finally { setBusy(false); }
  }

  async function saveReview(requirement: Requirement) {
    if (!selected) return;
    const draft = reviewDrafts[requirement.id] ?? {
      state: requirement.coverage_state, note: requirement.coverage_note ?? "",
    };
    setBusy(true); setError(null);
    try {
      await opportunityApi.reviewRequirement(selected, requirement, draft.state, draft.note.trim());
      await reloadCoverage(selected);
      setReviewDrafts((current) => {
        const next = { ...current }; delete next[requirement.id]; return next;
      });
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not save coverage decision");
    } finally { setBusy(false); }
  }

  const active = items.find((item) => item.id === selected);

  return <div className="opportunities-workspace">
    <header className="opportunities-heading">
      <div><span className="eyebrow">Sales workspace</span><h1>Opportunities</h1>
        <p>Turn customer needs into a reviewed solution and quote.</p></div>
    </header>
    {error && <div className="banner error" role="alert">{error}</div>}
    <div className="opportunities-grid">
      <aside className="opportunities-panel">
        <h2>Deals</h2>
        <form onSubmit={createOpportunity} className="opportunities-form">
          <label htmlFor="deal-title">New opportunity</label>
          <input id="deal-title" value={title} onChange={(e) => setTitle(e.target.value)} maxLength={255} placeholder="Customer project name" />
          <label htmlFor="deal-currency">Quote currency</label>
          <input id="deal-currency" value={currency} onChange={(e) => setCurrency(e.target.value.toUpperCase())} maxLength={3} pattern="[A-Z]{3}" />
          <button type="submit" disabled={busy || !title.trim()}>Create opportunity</button>
        </form>
        <div className="opportunities-list">
          {items.map((item) => <button key={item.id} type="button"
            className={selected === item.id ? "selected" : ""}
            onClick={() => { setSelected(item.id); setOffset(0); setReviewDrafts({}); }}>
            <strong>{item.title}</strong><span>{item.stage} · {item.currency}</span>
          </button>)}
          {items.length === 0 && <p className="muted">No opportunities yet.</p>}
        </div>
      </aside>
      <section className="opportunities-panel opportunities-detail">
        {!active ? <div className="opportunities-empty"><h2>Select an opportunity</h2><p>Review its customer requirements and coverage here.</p></div> : <>
          <div className="opportunities-detail-head"><div><span className="eyebrow">{active.stage}</span><h2>{active.title}</h2></div>
            <span className={`coverage-status ${coverage?.ready_for_quote ? "ready" : "pending"}`}>
              {coverage?.ready_for_quote ? "Coverage ready" : "Coverage needs review"}
            </span></div>
          <p className="muted">Mandatory requirements covered: {coverage?.mandatory_covered ?? 0} / {coverage?.mandatory_total ?? 0}</p>
          <div className="opportunities-inputs">
            <form onSubmit={addRequirement} className="opportunities-form">
              <label htmlFor="requirement-text">Add requirement</label>
              <textarea id="requirement-text" value={requirementText} onChange={(e) => setRequirementText(e.target.value)} maxLength={10000} placeholder="What must the solution provide?" />
              <button type="submit" disabled={busy || !requirementText.trim()}>Add</button>
            </form>
            <form onSubmit={importRequirements} className="opportunities-form">
              <label htmlFor="rfp-text">Paste RFP requirements</label>
              <textarea id="rfp-text" value={rfpText} onChange={(e) => setRfpText(e.target.value)} maxLength={100000} placeholder="Paste text containing must, shall, or required statements" />
              <button type="submit" disabled={busy || !rfpText.trim()}>Import mandatory items</button>
            </form>
          </div>
          <h3>Requirement coverage</h3>
          {coverage?.requirements.map((requirement) => {
            const draft = reviewDrafts[requirement.id] ?? { state: requirement.coverage_state, note: requirement.coverage_note ?? "" };
            return <article className="requirement-card" key={requirement.id}>
              <div className="requirement-copy"><span className="eyebrow">{requirement.priority}</span><p>{requirement.original_text}</p></div>
              <div className="requirement-review">
                <label htmlFor={`state-${requirement.id}`}>Coverage</label>
                <select id={`state-${requirement.id}`} value={draft.state} onChange={(e) => setReviewDrafts((current) => ({ ...current, [requirement.id]: { ...draft, state: e.target.value as Requirement["coverage_state"] } }))}>
                  {coverageStates.map((state) => <option key={state} value={state}>{state}</option>)}
                </select>
                <label htmlFor={`note-${requirement.id}`}>Review note</label>
                <input id={`note-${requirement.id}`} value={draft.note} onChange={(e) => setReviewDrafts((current) => ({ ...current, [requirement.id]: { ...draft, note: e.target.value } }))} maxLength={10000} placeholder="Evidence or gap explanation" />
                <button type="button" onClick={() => saveReview(requirement)} disabled={busy || (draft.state !== "unreviewed" && !draft.note.trim())}>Save review</button>
              </div>
            </article>;
          })}
          {coverage?.total === 0 && <p className="muted">Add or import requirements to start the coverage review.</p>}
          {coverage && coverage.total > coverage.limit && <div className="opportunities-pagination">
            <button type="button" disabled={offset === 0} onClick={() => setOffset(Math.max(0, offset - coverage.limit))}>Previous</button>
            <span>{offset + 1}–{Math.min(offset + coverage.limit, coverage.total)} of {coverage.total}</span>
            <button type="button" disabled={offset + coverage.limit >= coverage.total} onClick={() => setOffset(offset + coverage.limit)}>Next</button>
          </div>}
          <QuotePanel key={active.id} opportunityId={active.id} currency={active.currency} coverageReady={coverage?.ready_for_quote ?? false} />
          <ClaimsPanel key={`claims-${active.id}`} opportunityId={active.id} />
        </>}
      </section>
    </div>
  </div>;
}
