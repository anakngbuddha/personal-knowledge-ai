import { useState } from "react";

import { api } from "../services/api";
import type { WorkflowRun } from "../types";

interface Props {
  run: WorkflowRun;
}

export function DeliverableDownload({ run }: Props) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const exportTask = run.tasks.find((t) => t.slug === "export_deliverable");
  const ready = exportTask?.status === "succeeded";

  async function download() {
    setBusy(true);
    setError(null);
    try {
      const { blob, filename } = await api.downloadDeliverable(run.id);
      const url = URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = url;
      link.download = filename || "rfp-response.docx";
      document.body.appendChild(link);
      link.click();
      link.remove();
      URL.revokeObjectURL(url);
    } catch (err) {
      setError(err instanceof Error ? err.message : "deliverable not ready");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="deliverable-download">
      <button className="primary" disabled={!ready || busy} onClick={() => void download()}>
        {busy ? "Downloading…" : ready ? "Download .docx" : "Deliverable not ready"}
      </button>
      {error && <p className="doc-error">{error}</p>}
    </div>
  );
}
