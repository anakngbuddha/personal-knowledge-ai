import { useCallback, useEffect, useState } from "react";
import { api } from "../services/api";
import type { GraphEdge, KnowledgeDocument } from "../types";
import "../styles/source-insight.css";

interface Props {
  documentId: string | null;
  /** Called after an edit is saved so the list can pick up the new wording. */
  onChanged?: () => void;
}

/** Plain words for every relationship the map can hold. */
const RELATION_WORDS: Record<string, string> = {
  compatible: "works with",
  incompatible: "does not work with",
  conflicts_with: "clashes with",
  requires: "needs",
  replaces: "replaces",
  supersedes: "replaces",
  bundled_with: "is sold together with",
  recommended_with: "is recommended with",
  cross_sell: "pairs well with",
  upsell_to: "is a step up to",
  certified_for: "is certified for",
  requires_license: "needs a licence for",
  bundle_component: "is part of",
  suits_use_case: "suits"
};

function relationWords(relation: string): string {
  return RELATION_WORDS[relation] ?? relation.replace(/_/g, " ");
}

function confidenceWords(score: number | null | undefined): string | null {
  if (score === null || score === undefined) return null;
  if (score >= 0.75) return "Confident";
  if (score >= 0.5) return "Fairly sure";
  return "Worth checking";
}

function plainProblem(err: unknown, fallback: string): string {
  const raw = err instanceof Error ? err.message : String(err ?? "");
  const cleaned = raw.replace(/^[A-Za-z.]*(Error|Exception):\s*/, "").trim();
  return cleaned.length > 0 ? cleaned : fallback;
}

/**
 * "What I learned" (2.4). After a source is ready this shows the read-out in
 * plain language: the summary, what products it mentions, the facts worth
 * keeping, and any map suggestions still waiting on a person.
 */
export function SourceInsightCard({ documentId, onChanged }: Props) {
  const [doc, setDoc] = useState<KnowledgeDocument | null>(null);
  const [suggestions, setSuggestions] = useState<GraphEdge[]>([]);
  const [loading, setLoading] = useState(false);
  const [problem, setProblem] = useState<string | null>(null);
  const [editing, setEditing] = useState(false);
  const [saving, setSaving] = useState(false);
  const [summaryDraft, setSummaryDraft] = useState("");
  const [vendorDraft, setVendorDraft] = useState("");
  const [productsDraft, setProductsDraft] = useState("");
  const [validUntilDraft, setValidUntilDraft] = useState("");

  const load = useCallback(async () => {
    if (!documentId) {
      setDoc(null);
      setSuggestions([]);
      return;
    }
    setLoading(true);
    setProblem(null);
    try {
      const fetched = await api.getDocument(documentId);
      setDoc(fetched);
      try {
        const pending = await api.listEdges({ status: "pending_review" });
        setSuggestions(pending.filter((edge) => edge.document_id === documentId));
      } catch {
        // Map suggestions are a bonus here, never a reason to hide the read-out.
        setSuggestions([]);
      }
    } catch (err) {
      setProblem(plainProblem(err, "Could not open this source."));
      setDoc(null);
    } finally {
      setLoading(false);
    }
  }, [documentId]);

  useEffect(() => {
    void load();
    setEditing(false);
  }, [load]);

  function startEditing(current: KnowledgeDocument) {
    setSummaryDraft(current.summary ?? "");
    setVendorDraft(current.vendor ?? "");
    setProductsDraft((current.products_referenced ?? []).join(", "));
    setValidUntilDraft((current.valid_until ?? "").slice(0, 10));
    setProblem(null);
    setEditing(true);
  }

  async function save() {
    if (!doc) return;
    setSaving(true);
    setProblem(null);
    try {
      const products = productsDraft
        .split(",")
        .map((item) => item.trim())
        .filter((item) => item.length > 0);
      const updated = await api.updateDocument(doc.id, {
        summary: summaryDraft.trim().length > 0 ? summaryDraft.trim() : null,
        vendor: vendorDraft.trim().length > 0 ? vendorDraft.trim() : null,
        products_referenced: products.length > 0 ? products : null,
        valid_until: validUntilDraft.length > 0 ? validUntilDraft : null
      });
      setDoc(updated);
      setEditing(false);
      onChanged?.();
    } catch (err) {
      setProblem(plainProblem(err, "Could not save your changes."));
    } finally {
      setSaving(false);
    }
  }

  async function accept(edgeId: string) {
    try {
      await api.approveEdge(edgeId);
      setSuggestions((current) => current.filter((edge) => edge.id !== edgeId));
    } catch (err) {
      setProblem(plainProblem(err, "Could not add that to the map."));
    }
  }

  async function dismiss(edgeId: string) {
    try {
      await api.rejectEdge(edgeId, "Not right for our map");
      setSuggestions((current) => current.filter((edge) => edge.id !== edgeId));
    } catch (err) {
      setProblem(plainProblem(err, "Could not dismiss that suggestion."));
    }
  }

  if (!documentId) return null;
  if (loading && !doc) return <p className="muted">Opening this source…</p>;
  if (!doc) {
    return problem ? <p className="insight-problem">{problem}</p> : null;
  }

  if (doc.status === "failed") {
    return (
      <section className="source-insight">
        <header>
          <div>
            <p className="insight-kicker">What I learned</p>
            <h3>{doc.title || doc.original_filename}</h3>
          </div>
        </header>
        <p className="insight-summary">
          {doc.error_message || "This file could not be added. Try again, or upload a text version."}
        </p>
      </section>
    );
  }

  if (doc.status !== "ready") {
    return (
      <section className="source-insight">
        <header>
          <div>
            <p className="insight-kicker">What I learned</p>
            <h3>{doc.title || doc.original_filename}</h3>
          </div>
        </header>
        <p className="insight-summary">Still reading this one. The read-out shows up here when it is ready to ask about.</p>
        <div className="insight-actions">
          <button type="button" onClick={() => void load()}>
            Check again
          </button>
        </div>
      </section>
    );
  }

  const products = doc.detected_products ?? doc.products_referenced ?? [];
  const facts = doc.key_facts ?? [];
  const tags = doc.topic_tags ?? [];
  const confidence = confidenceWords(doc.understanding_confidence);

  return (
    <section className="source-insight">
      <header>
        <div>
          <p className="insight-kicker">What I learned</p>
          <h3>{doc.title || doc.original_filename}</h3>
        </div>
        {!editing && (
          <button type="button" className="link-button" onClick={() => startEditing(doc)}>
            Edit
          </button>
        )}
      </header>

      {editing ? (
        <div className="insight-edit">
          <label>
            Summary
            <textarea value={summaryDraft} onChange={(e) => setSummaryDraft(e.target.value)} />
          </label>
          <label>
            Brand or maker
            <input value={vendorDraft} onChange={(e) => setVendorDraft(e.target.value)} placeholder="Jabra" />
          </label>
          <label>
            Products it covers (comma separated)
            <input
              value={productsDraft}
              onChange={(e) => setProductsDraft(e.target.value)}
              placeholder="PanaCast 50, Speak2 75"
            />
          </label>
          <label>
            Good until
            <input type="date" value={validUntilDraft} onChange={(e) => setValidUntilDraft(e.target.value)} />
          </label>
          <div className="insight-actions">
            <button type="button" onClick={() => void save()} disabled={saving}>
              {saving ? "Saving…" : "Save"}
            </button>
            <button type="button" className="link-button" onClick={() => setEditing(false)} disabled={saving}>
              Cancel
            </button>
          </div>
          {problem && <p className="insight-problem">{problem}</p>}
        </div>
      ) : (
        <>
          <p className="insight-summary">
            {doc.summary || "No read-out for this source yet. You can write one here so answers describe it the way you would."}
          </p>

          {products.length > 0 && (
            <div className="insight-block">
              <span className="insight-label">Products it mentions</span>
              <div className="chips">
                {products.map((name) => (
                  <span className="chip" key={name}>
                    {name}
                  </span>
                ))}
              </div>
            </div>
          )}

          {facts.length > 0 && (
            <div className="insight-block">
              <span className="insight-label">Worth remembering</span>
              <ul className="insight-facts">
                {facts.map((fact, index) => (
                  <li key={`${fact.label}-${index}`}>
                    <span className="fact-label">{fact.label}</span>
                    <span>{fact.value}</span>
                  </li>
                ))}
              </ul>
            </div>
          )}

          {tags.length > 0 && (
            <div className="insight-block">
              <span className="insight-label">Topics</span>
              <div className="chips">
                {tags.map((tag) => (
                  <span className="chip" key={tag}>
                    {tag}
                  </span>
                ))}
              </div>
            </div>
          )}

          {suggestions.length > 0 && (
            <div className="insight-block">
              <span className="insight-label">Suggested for your map</span>
              <ul className="insight-suggestions">
                {suggestions.map((edge) => (
                  <li key={edge.id}>
                    <span className="suggestion-text">
                      <strong>{edge.source_product_name}</strong> {relationWords(edge.relation_type)}{" "}
                      <strong>{edge.target_product_name}</strong>
                    </span>
                    <button type="button" onClick={() => void accept(edge.id)}>
                      Add to map
                    </button>
                    <button type="button" className="link-button" onClick={() => void dismiss(edge.id)}>
                      Not this one
                    </button>
                  </li>
                ))}
              </ul>
            </div>
          )}

          <p className="insight-note">
            {[
              doc.detected_doc_type ? `Looks like a ${doc.detected_doc_type.replace(/_/g, " ")}` : null,
              doc.detected_version_label ? `Version ${doc.detected_version_label}` : null,
              doc.ocr_applied ? "Read with OCR" : null,
              confidence
            ]
              .filter((part): part is string => Boolean(part))
              .join(" · ")}
          </p>
          {problem && <p className="insight-problem">{problem}</p>}
        </>
      )}
    </section>
  );
}
