import { useEffect, useMemo, useState } from "react";

import { api } from "../services/api";
import { DeliverableDownload } from "./DeliverableDownload";
import { HitlReviewModal } from "./HitlReviewModal";
import { PlaybookGallery } from "./PlaybookGallery";
import { TaskTree } from "./TaskTree";
import { usePlaybookGallery, usePrincipal, useWorkflowRun } from "../hooks/useWorkflows";
import type { RfpAnswer, RfpAnswerEdit, WorkflowTask } from "../types";

function answersFrom(task: WorkflowTask | undefined): RfpAnswer[] {
  const raw = task?.output_payload?.answers;
  return Array.isArray(raw) ? (raw as RfpAnswer[]) : [];
}

export function WorkflowWorkspace() {
  const principal = usePrincipal();
  const gallery = usePlaybookGallery();
  const [runId, setRunId] = useState<string | null>(null);
  const { run, setRun, error, setError, loading, refresh } = useWorkflowRun(runId);
  const [selectedSlug, setSelectedSlug] = useState<string | null>(null);
  const [hitlOpen, setHitlOpen] = useState(false);
  const [busy, setBusy] = useState(false);

  const waiting = useMemo(
    () => run?.tasks.find((t) => t.status === "waiting_approval"),
    [run]
  );

  useEffect(() => {
    if (waiting) {
      setHitlOpen(true);
      setSelectedSlug(waiting.slug);
    }
  }, [waiting?.id]);

  const canWrite = Boolean(principal?.can_write_catalog);
  const answers = answersFrom(waiting);

  async function approve(edits: RfpAnswerEdit[]) {
    if (!run || !waiting) return;
    setBusy(true);
    setError(null);
    try {
      const next = await api.approveTask(run.id, waiting.slug, edits);
      setRun(next);
      setHitlOpen(false);
    } catch (err) {
      setError(err instanceof Error ? err.message : "approve failed");
    } finally {
      setBusy(false);
    }
  }

  async function reject(reason: string) {
    if (!run || !waiting) return;
    setBusy(true);
    setError(null);
    try {
      const next = await api.rejectTask(run.id, waiting.slug, reason);
      setRun(next);
      setHitlOpen(false);
    } catch (err) {
      setError(err instanceof Error ? err.message : "reject failed");
    } finally {
      setBusy(false);
    }
  }

  if (!runId) {
    return (
      <div className="workflow-workspace">
        {gallery.error && <div className="banner error">{gallery.error}</div>}
        <PlaybookGallery
          playbooks={gallery.playbooks}
          runs={gallery.runs}
          total={gallery.total}
          offset={gallery.offset}
          pageSize={gallery.pageSize}
          loading={gallery.loading}
          canStart={canWrite}
          authReady={principal !== null}
          onOpenRun={setRunId}
          onStarted={(id) => {
            setRunId(id);
            void gallery.refresh();
          }}
          onPage={(next) => void gallery.refresh(next)}
          onError={gallery.setError}
        />
      </div>
    );
  }

  return (
    <div className="workflow-workspace">
      <div className="workflow-toolbar">
        <button
          onClick={() => {
            setRunId(null);
            void gallery.refresh();
          }}
        >
          Index
        </button>
        <div>
          <p className="kicker">Active run</p>
          <strong>{run?.playbook_slug ?? "Loading run"}</strong>
          {run && (
            <span
              className={`badge ${run.status === "succeeded" ? "ready" : run.status === "failed" ? "failed" : "processing"}`}
            >
              {run.status === "waiting_approval" ? "Waiting approval" : run.status.replace("_", " ")}
            </span>
          )}
        </div>
        <button onClick={() => void refresh()} disabled={loading}>
          Refresh
        </button>
        {run && <DeliverableDownload run={run} />}
      </div>
      {(error || gallery.error) && <div className="banner error">{error || gallery.error}</div>}
      {run?.error_message && <div className="banner error">{run.error_message}</div>}
      {loading && !run && <p className="muted">Loading the run sheet…</p>}
      {run && (
        <TaskTree
          tasks={run.tasks}
          selectedSlug={selectedSlug}
          onSelect={setSelectedSlug}
        />
      )}
      {waiting && !hitlOpen && (
        <button className="primary" onClick={() => setHitlOpen(true)}>
          Open waiting-approval review
        </button>
      )}
      {hitlOpen && waiting && (
        <HitlReviewModal
          answers={answers}
          canApprove={canWrite}
          busy={busy}
          onApprove={(edits) => void approve(edits)}
          onReject={(reason) => void reject(reason)}
          onClose={() => setHitlOpen(false)}
        />
      )}
    </div>
  );
}
