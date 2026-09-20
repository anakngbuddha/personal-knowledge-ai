import { useEffect, useMemo, useState } from "react";

import type { RfpAnswer, RfpAnswerEdit } from "../types";

interface Props {
  answers: RfpAnswer[];
  canApprove: boolean;
  busy: boolean;
  onApprove: (edits: RfpAnswerEdit[]) => void;
  onReject: (reason: string) => void;
  onClose: () => void;
}

function conflictWarnings(answer: RfpAnswer): string[] {
  const warnings: string[] = [];
  if (answer.unmet_prerequisites) warnings.push("Unmet prerequisites flagged.");
  for (const product of answer.candidate_products ?? []) {
    for (const item of product.impact?.all_incompatibilities ?? []) {
      if (item.conflicted_product_name) {
        warnings.push(`${product.name ?? "product"} conflicts with ${item.conflicted_product_name}`);
      }
    }
  }
  return warnings;
}

function toEdits(answers: RfpAnswer[]): RfpAnswerEdit[] {
  return answers
    .filter((row) => row.id)
    .map((row) => ({
      id: String(row.id),
      response: row.response ?? "",
      status: row.status ?? "Partially",
    }));
}

export function HitlReviewModal({ answers, canApprove, busy, onApprove, onReject, onClose }: Props) {
  const [drafts, setDrafts] = useState<RfpAnswer[]>(answers);
  const [index, setIndex] = useState(0);
  const [reason, setReason] = useState("");

  useEffect(() => {
    setDrafts(answers);
    setIndex(0);
  }, [answers]);

  const current = drafts[index];
  const warnings = useMemo(() => (current ? conflictWarnings(current) : []), [current]);

  function patch(partial: Partial<RfpAnswer>) {
    setDrafts((rows) => rows.map((row, i) => (i === index ? { ...row, ...partial } : row)));
  }

  if (!current) {
    return (
      <div className="modal-backdrop" onClick={onClose}>
        <div className="modal-card hitl-modal" onClick={(e) => e.stopPropagation()}>
          <div className="modal-header">
            <h3>HITL review</h3>
            <button onClick={onClose}>Close</button>
          </div>
          <p className="muted">No drafted answers to review.</p>
        </div>
      </div>
    );
  }

  return (
    <div className="modal-backdrop">
      <div className="modal-card hitl-modal" onClick={(e) => e.stopPropagation()}>
        <div className="modal-header">
          <h3>
            HITL review {index + 1} / {drafts.length}
          </h3>
          <button onClick={onClose} disabled={busy}>
            Close
          </button>
        </div>

        <div className="hitl-grid">
          <section>
            <h4>Requirement</h4>
            <p>{current.text || "(no text)"}</p>
            <p className="muted">
              {current.id} {current.section ? `· ${current.section}` : ""}{" "}
              {current.must_have ? "· must-have" : ""}
            </p>
          </section>
          <section>
            <h4>Drafted response</h4>
            <textarea
              value={current.response ?? ""}
              maxLength={8000}
              rows={6}
              onChange={(e) => patch({ response: e.target.value })}
              disabled={!canApprove || busy}
            />
            <label>
              Status
              <select
                value={current.status ?? "Partially"}
                onChange={(e) => patch({ status: e.target.value })}
                disabled={!canApprove || busy}
              >
                <option>Compliant</option>
                <option>Partially</option>
                <option>Non-Compliant</option>
              </select>
            </label>
          </section>
          <section>
            <h4>Citations</h4>
            {(current.citations ?? []).length === 0 && <p className="muted">No citations.</p>}
            <ul>
              {(current.citations ?? []).map((cite) => (
                <li key={cite}>{cite}</li>
              ))}
            </ul>
            {(current.products ?? []).length > 0 && (
              <p className="muted">Products: {(current.products ?? []).join(", ")}</p>
            )}
          </section>
          <section>
            <h4>Graph warnings</h4>
            {warnings.length === 0 && <p className="health-alert success">No conflict warnings.</p>}
            {warnings.map((w) => (
              <p key={w} className="health-alert danger">
                {w}
              </p>
            ))}
            {typeof current.confidence === "number" && (
              <p className="muted">confidence {current.confidence}</p>
            )}
          </section>
        </div>

        <div className="hitl-nav">
          <button disabled={index === 0 || busy} onClick={() => setIndex((i) => i - 1)}>
            Previous
          </button>
          <button disabled={index >= drafts.length - 1 || busy} onClick={() => setIndex((i) => i + 1)}>
            Next
          </button>
        </div>

        {canApprove ? (
          <div className="hitl-actions">
            <button className="approve-btn" disabled={busy} onClick={() => onApprove(toEdits(drafts))}>
              {busy ? "Saving…" : "Approve & Resume"}
            </button>
            <input
              type="text"
              className="search-input"
              placeholder="Reject reason"
              maxLength={2000}
              value={reason}
              onChange={(e) => setReason(e.target.value)}
              disabled={busy}
            />
            <button className="reject-btn" disabled={busy} onClick={() => onReject(reason.trim() || "rejected")}>
              Reject
            </button>
          </div>
        ) : (
          <p className="hint">View only — solutions engineer role required to approve.</p>
        )}
      </div>
    </div>
  );
}
