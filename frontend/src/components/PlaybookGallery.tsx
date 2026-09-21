import { useState } from "react";
import { api } from "../services/api";
import type { Playbook, WorkflowRunSummary } from "../types";

interface Props { playbooks: Playbook[]; runs: WorkflowRunSummary[]; total: number; offset: number; pageSize: number; loading: boolean; canStart: boolean; authReady: boolean; onOpenRun: (id: string) => void; onStarted: (id: string) => void; onPage: (offset: number) => void; onError: (message: string | null) => void; }

function statusClass(status: string): string { return status === "succeeded" ? "ready" : status === "failed" ? "failed" : status === "waiting_approval" ? "processing" : "uploaded"; }

export function PlaybookGallery(props: Props) {
  const [file, setFile] = useState<File | null>(null);
  const [accountRef, setAccountRef] = useState("");
  const [notes, setNotes] = useState("");
  const [logs, setLogs] = useState("");
  const [installBase, setInstallBase] = useState("");
  const [product, setProduct] = useState("");
  const [version, setVersion] = useState("");
  const [starting, setStarting] = useState(false);

  async function start(action: () => Promise<{ id: string }>) {
    if (!props.canStart) return;
    setStarting(true); props.onError(null);
    try { const run = await action(); props.onStarted(run.id); }
    catch (err) { props.onError(err instanceof Error ? err.message : "failed to start playbook"); }
    finally { setStarting(false); }
  }
  const meta = (slug: string, fallback: number) => props.playbooks.find((p) => p.slug === slug)?.task_count ?? fallback;

  return <div className="workflow-gallery">
    <section className="playbook-grid">
      <article className="playbook-card"><header><h3>RFP Responder</h3><span className="badge ready">Runnable</span></header><p>Ground a questionnaire in approved catalog evidence, review it, then export Word.</p><p className="playbook-meta">{meta("rfp-response", 6)} tasks</p><input type="file" accept=".csv,.xlsx" onChange={(e) => setFile(e.target.files?.[0] ?? null)} /><input className="search-input" placeholder="Account ref (optional)" value={accountRef} onChange={(e) => setAccountRef(e.target.value)} /><button className="primary" disabled={!file || !props.canStart || starting} onClick={() => file && void start(() => api.startRfpRun(file, accountRef || undefined))}>Start RFP run</button></article>
      <article className="playbook-card"><header><h3>Solution Composer</h3><span className="badge ready">Phase 8</span></header><p>Turn discovery notes into a graph-validated HLD and BOM with an approval gate.</p><p className="playbook-meta">{meta("solution-composer", 6)} tasks</p><textarea rows={6} maxLength={50000} placeholder="Paste discovery notes and constraints" value={notes} onChange={(e) => setNotes(e.target.value)} /><button className="primary" disabled={!notes.trim() || !props.canStart || starting} onClick={() => void start(() => api.startSolutionComposer(notes, accountRef || undefined))}>Compose solution</button></article>
      <article className="playbook-card"><header><h3>Incident Triage</h3><span className="badge ready">Phase 8</span></header><p>Analyze logs as untrusted data, traverse dependencies, and export a cited runbook.</p><p className="playbook-meta">{meta("incident-triage", 5)} tasks</p><input className="search-input" placeholder="Installed products, comma separated" value={installBase} onChange={(e) => setInstallBase(e.target.value)} /><textarea rows={5} maxLength={50000} placeholder="Paste error logs" value={logs} onChange={(e) => setLogs(e.target.value)} /><button className="primary" disabled={!logs.trim() || !installBase.trim() || !props.canStart || starting} onClick={() => void start(() => api.startIncidentTriage(logs, installBase.split(",").map((x) => x.trim()).filter(Boolean)))}>Build runbook</button></article>
      <article className="playbook-card"><header><h3>Upgrade Impact Audit</h3><span className="badge ready">Phase 8</span></header><p>Trace transitive prerequisites, breakage, integrations, and alternatives before an upgrade.</p><p className="playbook-meta">{meta("upgrade-impact", 3)} tasks</p><input className="search-input" placeholder="Product name or slug" value={product} onChange={(e) => setProduct(e.target.value)} /><input className="search-input" placeholder="Proposed version (optional)" value={version} onChange={(e) => setVersion(e.target.value)} /><button className="primary" disabled={!product.trim() || !props.canStart || starting} onClick={() => void start(() => api.startUpgradeImpact(product, version || undefined))}>Audit upgrade</button></article>
    </section>
    {!props.canStart && props.authReady && <p className="hint">Solutions engineer role required to start a playbook.</p>}
    <section className="panel recent-runs"><div className="panel-head"><h2>Recent runs ({props.total})</h2></div>{props.loading && <p className="muted">Loading…</p>}<ul className="run-list">{props.runs.map((run) => <li key={run.id}><button className="run-row" onClick={() => props.onOpenRun(run.id)}><span className="run-slug">{run.playbook_slug}</span><span className={`badge ${statusClass(run.status)}`}>{run.status.replace("_", " ")}</span><span className="run-meta">{run.task_counts.succeeded}/{Object.values(run.task_counts).reduce((a, b) => a + b, 0)} tasks</span><span className="run-meta">{new Date(run.created_at).toLocaleString()}</span></button></li>)}</ul>{props.total > props.pageSize && <div className="pager"><button disabled={props.offset <= 0} onClick={() => props.onPage(Math.max(0, props.offset - props.pageSize))}>Previous</button><button disabled={props.offset + props.pageSize >= props.total} onClick={() => props.onPage(props.offset + props.pageSize)}>Next</button></div>}</section>
  </div>;
}
