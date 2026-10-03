import { useEffect, useState } from "react";
import type { PrincipalProfile } from "../types";
import { opportunityApi } from "../services/opportunities";
import type { Coverage, Opportunity } from "../services/opportunities";
import { QuotePanel } from "./QuotePanel";
import { ClaimsPanel } from "./ClaimsPanel";
import { TenantPricingSetup } from "./TenantPricingSetup";
import "../styles/opportunities.css";
import "../styles/battleQuote.css";

interface Props {
  principal: PrincipalProfile | null;
  opportunityId?: string | null;
  onSelectOpportunity: (id: string) => void;
  onOpenOpportunity: (id?: string) => void;
}

export function BattleQuoteWorkspace({ principal, opportunityId, onSelectOpportunity, onOpenOpportunity }: Props) {
  const [section, setSection] = useState<"quotes" | "claims" | "setup">("quotes");
  const [items, setItems] = useState<Opportunity[]>([]);
  const [selected, setSelected] = useState<Opportunity | null>(null);
  const [offset, setOffset] = useState(0);
  const [coverage, setCoverage] = useState<Coverage | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [revision, setRevision] = useState(0);
  const admin = Boolean(principal?.is_admin || principal?.is_owner);
  const canUseSales = Boolean(principal?.user_id && (admin || principal.can_write_catalog || principal.role === "sales"));

  useEffect(() => {
    if (!canUseSales) { setLoading(false); return; }
    let active = true;
    setLoading(true); setError(null);
    opportunityApi.list(offset).then((result) => {
      if (!active) return;
      setItems(result.items);
    }).catch((err: unknown) => { if (active) setError(err instanceof Error ? err.message : "Could not load opportunities."); })
      .finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, [offset, canUseSales, revision]);

  useEffect(() => {
    if (!opportunityId || !canUseSales) { setCoverage(null); setSelected(null); return; }
    let active = true;
    setCoverage(null); setSelected(null); setError(null);
    Promise.all([opportunityApi.get(opportunityId), opportunityApi.coverage(opportunityId)])
      .then(([deal, next]) => { if (active) { setSelected(deal); setCoverage(next); } })
      .catch((err: unknown) => { if (active) setError(err instanceof Error ? err.message : "Could not load this opportunity. Try again."); });
    return () => { active = false; };
  }, [opportunityId, canUseSales, revision]);

  return <div className="opportunities-workspace battle-quote-workspace">
    <header className="opportunities-heading battle-heading"><div><h1>Battle Quote</h1><p>Build cloud quotations and customer battle cards from reviewed prices and evidence.</p></div>
      <button type="button" className="battle-secondary" onClick={() => onOpenOpportunity()}>Manage opportunities</button>
    </header>
    {!principal ? <p role="status">Loading your access…</p> : !canUseSales ? <p className="battle-feedback">A sales, solutions engineer, or administrator role is required. Ask your tenant administrator for access.</p> : <>
      <nav className="battle-section-nav" aria-label="Battle Quote sections">
        <button type="button" aria-current={section === "quotes" ? "page" : undefined} onClick={() => setSection("quotes")}>Quotes</button>
        <button type="button" aria-current={section === "claims" ? "page" : undefined} onClick={() => setSection("claims")}>Battle cards</button>
        <button type="button" aria-current={section === "setup" ? "page" : undefined} onClick={() => setSection("setup")}>Tenant setup</button>
      </nav>
      {section === "setup" ? admin ? <TenantPricingSetup onChanged={() => setRevision((value) => value + 1)} />
        : <section className="battle-setup-section"><h2>Tenant setup</h2><p>Your tenant administrator configures Azure, AWS, Huawei Cloud, and Google Cloud pricing access, approves SKU mappings, and creates list-price policies.</p><p>Quote approval requires a separate administrator. Battle-card claims require a separate solutions engineer reviewer and an approved evidence source.</p></section>
        : <>
          {error && <div className="banner error" role="alert">{error}<button type="button" className="battle-secondary" onClick={() => setRevision((value) => value + 1)}>Retry loading</button></div>}
          <div className="battle-deal-picker">
            <label htmlFor="battle-opportunity">Opportunity</label>
            <select id="battle-opportunity" value={opportunityId || ""} disabled={loading} onChange={(event) => { setSelected(items.find((item) => item.id === event.target.value) ?? null); onSelectOpportunity(event.target.value); }}>
              <option value="">Choose an opportunity</option>
              {selected && !items.some((item) => item.id === selected.id) && <option value={selected.id}>{selected.title} · {selected.currency}</option>}
              {items.map((item) => <option key={item.id} value={item.id}>{item.title} · {item.currency}</option>)}
            </select>
            <div className="battle-pagination"><button type="button" disabled={loading || offset === 0} onClick={() => setOffset(Math.max(0, offset - 50))}>Previous opportunities</button><button type="button" disabled={loading || items.length < 50} onClick={() => setOffset(offset + 50)}>More opportunities</button></div>
          </div>
          {loading && <p role="status">Loading opportunities…</p>}
          {!opportunityId ? <div className="opportunities-empty"><h2>Choose a customer opportunity</h2><p>Select a deal to create its quote or review its battle-card claims.</p><button type="button" className="battle-secondary" onClick={() => onOpenOpportunity()}>Create an opportunity</button></div> : <>
            <div className="battle-coverage"><span className={`coverage-status ${coverage?.ready_for_quote ? "ready" : "pending"}`}>{coverage ? coverage.ready_for_quote ? "Coverage ready" : "Coverage needs review" : "Loading coverage…"}</span>
              <button type="button" className="battle-secondary" onClick={() => onOpenOpportunity(opportunityId)}>Review requirements</button>
            </div>
            {section === "quotes" && (selected?.id === opportunityId ? <QuotePanel key={`${selected.id}-${revision}`} opportunityId={selected.id} currency={selected.currency} coverageReady={coverage?.ready_for_quote ?? false} canApprove={admin} onSetup={() => setSection("setup")} /> : !error && <p role="status">Loading the selected opportunity…</p>)}
            {section === "claims" && <ClaimsPanel key={opportunityId} opportunityId={opportunityId} canReview={Boolean(principal.can_write_catalog)} />}
          </>}
        </>}
    </>}
  </div>;
}
