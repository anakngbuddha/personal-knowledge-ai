import { useEffect, useState } from "react";
import { salesClaimsApi } from "../services/salesClaims";
import type { BattleCardClaim, ClaimSource, SalesClaim } from "../services/salesClaims";

export function ClaimsPanel({ opportunityId }: { opportunityId: string }) {
  const [claims, setClaims] = useState<SalesClaim[]>([]);
  const [sources, setSources] = useState<ClaimSource[]>([]);
  const [statement, setStatement] = useState("");
  const [competitor, setCompetitor] = useState("");
  const [sourceId, setSourceId] = useState("");
  const [anchor, setAnchor] = useState("");
  const [validUntil, setValidUntil] = useState("");
  const [reasons, setReasons] = useState<Record<string, string>>({});
  const [offset, setOffset] = useState(0);
  const [sourceOffset, setSourceOffset] = useState(0);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [card, setCard] = useState<BattleCardClaim[] | null>(null);

  useEffect(() => {
    let active = true;
    Promise.all([salesClaimsApi.list(opportunityId, offset), salesClaimsApi.sources(opportunityId, sourceOffset)])
      .then(([a, b]) => { if (active) { setClaims(a.items); setSources(b.items); setError(null); } })
      .catch((err: unknown) => { if (active) setError(err instanceof Error ? err.message : "Could not load reviewed claims"); });
    return () => { active = false; };
  }, [opportunityId, offset, sourceOffset]);

  async function create(event: React.FormEvent) {
    event.preventDefault(); setBusy(true); setError(null);
    try {
      await salesClaimsApi.create(opportunityId, { statement: statement.trim(), competitor: competitor.trim() || undefined,
        source_document_id: sourceId, source_anchor: anchor.trim(), valid_until: validUntil });
      setClaims((await salesClaimsApi.list(opportunityId, offset)).items);
      setStatement(""); setAnchor(""); setCard(null);
    } catch (err) { setError(err instanceof Error ? err.message : "Could not save claim"); }
    finally { setBusy(false); }
  }

  async function decide(claim: SalesClaim, action: "approve" | "revoke") {
    setBusy(true); setError(null);
    try {
      await salesClaimsApi.decide(claim.id, action, claim.version, reasons[claim.id].trim());
      setClaims((await salesClaimsApi.list(opportunityId, offset)).items); setCard(null);
    } catch (err) { setError(err instanceof Error ? err.message : "Could not review claim"); }
    finally { setBusy(false); }
  }

  async function preview() {
    setBusy(true); setError(null);
    try { setCard((await salesClaimsApi.battleCard(opportunityId, offset)).items); }
    catch (err) { setError(err instanceof Error ? err.message : "Could not export battle card"); }
    finally { setBusy(false); }
  }

  return <section className="quote-panel" aria-label="Reviewed sales claims">
    <h3>Reviewed claims</h3>
    <p className="muted">Research becomes reusable after a separate reviewer checks an approved source. Customer-safe battle cards include current public evidence.</p>
    {error && <div role="alert" className="banner error">{error}</div>}
    <form onSubmit={create} className="opportunities-form">
      <label htmlFor="claim-statement">Statement</label><textarea id="claim-statement" maxLength={4000} value={statement} onChange={(e) => setStatement(e.target.value)} required />
      <label htmlFor="claim-competitor">Competitor or vendor</label><input id="claim-competitor" maxLength={255} value={competitor} onChange={(e) => setCompetitor(e.target.value)} />
      <label htmlFor="claim-source">Evidence source</label><select id="claim-source" value={sourceId} onChange={(e) => setSourceId(e.target.value)} required><option value="">Choose a source</option>{sources.map((source) => <option key={source.id} value={source.id}>{source.title} · v{source.version} · {source.approval_state}</option>)}</select>
      <div><button type="button" disabled={sourceOffset === 0 || busy} onClick={() => { setSourceOffset(Math.max(0, sourceOffset - 50)); setSourceId(""); }}>Previous sources</button><button type="button" disabled={sources.length < 50 || busy} onClick={() => { setSourceOffset(sourceOffset + 50); setSourceId(""); }}>More sources</button></div>
      <label htmlFor="claim-anchor">Page or section</label><input id="claim-anchor" maxLength={512} value={anchor} onChange={(e) => setAnchor(e.target.value)} required />
      <label htmlFor="claim-validity">Valid until</label><input id="claim-validity" type="date" value={validUntil} onChange={(e) => setValidUntil(e.target.value)} required />
      <button disabled={busy || !statement.trim() || !sourceId || !anchor.trim() || !validUntil}>Save draft claim</button>
    </form>
    {claims.map((claim) => <article key={claim.id} className="quote-version"><strong>{claim.status}</strong><p>{claim.statement}</p><p>{claim.source_anchor} · source v{claim.source_version} · valid until {claim.valid_until}</p>
      {claim.review_reason && <p>{claim.review_reason}</p>}
      {claim.status !== "revoked" && <><label htmlFor={`reason-${claim.id}`}>Review rationale</label><input id={`reason-${claim.id}`} maxLength={2000} value={reasons[claim.id] || ""} onChange={(e) => setReasons((r) => ({ ...r, [claim.id]: e.target.value }))} />
        {claim.status === "draft" && <button disabled={busy || !reasons[claim.id]?.trim()} onClick={() => decide(claim, "approve")}>Approve claim (reviewer)</button>}<button disabled={busy || !reasons[claim.id]?.trim()} onClick={() => decide(claim, "revoke")}>Revoke claim</button></>}
    </article>)}
    <div><button disabled={busy || offset === 0} onClick={() => { setOffset(Math.max(0, offset - 50)); setCard(null); }}>Previous claims</button><button disabled={busy || claims.length < 50} onClick={() => { setOffset(offset + 50); setCard(null); }}>More claims</button></div>
    <button disabled={busy} onClick={preview}>Preview customer-safe battle card</button>
    {card && <div aria-label="Battle card preview">{card.length === 0 ? <p>No current public claims approved for this page.</p> : card.map((claim) => <article key={claim.id}><p>{claim.statement}</p><p>{claim.source.anchor} · source v{claim.source.version}</p>{claim.source.url && /^https?:\/\//i.test(claim.source.url) && <a href={claim.source.url} target="_blank" rel="noopener noreferrer">Read cited source</a>}</article>)}</div>}
  </section>;
}
