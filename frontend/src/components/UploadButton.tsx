import { useEffect, useRef, useState } from "react";
import type { ChangeEvent, DragEvent } from "react";

import { FolderIcon, UploadCloudIcon } from "./Icons";
import { api } from "../services/api";
import type { DocumentStatusReport, TrackedUpload, UploadPhase } from "../types";

interface Props {
  onUploaded: () => void;
  onError: (message: string) => void;
}

const ACCEPT = ".pdf,.docx,.pptx,.xlsx,.txt,.md,.html";
const POLL_MS = 2000;

const PHASE_LABEL: Record<UploadPhase, string> = {
  queued: "Waiting",
  reading: "Reading the file",
  understanding: "Working out what it says",
  ready: "Ready to ask about",
  failed: "Could not be added",
};

let counter = 0;
function nextKey(): string {
  counter += 1;
  return `u${counter}`;
}

/** Backend status plus chunk count, in words a salesperson can read. */
function phaseFor(report: DocumentStatusReport): UploadPhase {
  if (report.status === "ready") return "ready";
  if (report.status === "failed" || report.status === "quarantined") return "failed";
  if (report.status === "processing") {
    return report.chunk_count > 0 ? "understanding" : "reading";
  }
  return "queued";
}

export function UploadButton({ onUploaded, onError }: Props) {
  const fileInputRef = useRef<HTMLInputElement>(null);
  const folderInputRef = useRef<HTMLInputElement>(null);
  const [items, setItems] = useState<TrackedUpload[]>([]);
  const [busy, setBusy] = useState(false);
  const [dragging, setDragging] = useState(false);

  // The folder picker is not in the React typings and is not in every browser.
  useEffect(() => {
    const el = folderInputRef.current;
    if (!el) return;
    el.setAttribute("webkitdirectory", "");
    el.setAttribute("directory", "");
  }, []);

  // Poll anything still in flight. One timer per settle, so a long batch does not
  // stack requests.
  useEffect(() => {
    const pending = items.filter(
      (item) => item.documentId && item.phase !== "ready" && item.phase !== "failed"
    );
    if (pending.length === 0) return;

    const timer = setTimeout(async () => {
      const updates = await Promise.all(
        pending.map(async (item) => {
          try {
            const report = await api.documentStatus(item.documentId as string);
            return { key: item.key, phase: phaseFor(report), detail: report.error_message };
          } catch {
            return null;
          }
        })
      );
      let reachedReady = false;
      setItems((prev) =>
        prev.map((item) => {
          const update = updates.find((u) => u && u.key === item.key);
          if (!update) return item;
          if (update.phase === "ready" && item.phase !== "ready") reachedReady = true;
          return { ...item, phase: update.phase, detail: update.detail ?? item.detail };
        })
      );
      if (reachedReady) onUploaded();
    }, POLL_MS);

    return () => clearTimeout(timer);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [items]);

  async function addFiles(files: File[]) {
    if (files.length === 0) return;
    const tracked: TrackedUpload[] = files.map((file) => ({
      key: nextKey(),
      filename: file.name,
      file,
      phase: "queued",
      documentId: null,
      detail: null,
    }));
    setItems((prev) => [...tracked, ...prev]);
    setBusy(true);

    try {
      const res = await api.uploadDocuments(files);
      const byName = new Map<string, TrackedUpload>();
      tracked.forEach((item) => {
        if (!byName.has(item.filename)) byName.set(item.filename, item);
      });

      setItems((prev) =>
        prev.map((item) => {
          if (!tracked.some((t) => t.key === item.key)) return item;
          const report = res.results.find((r) => r.original_filename === item.filename);
          if (!report) return item;
          if (report.status === "rejected") {
            return { ...item, phase: "failed", detail: plainRejection(report.detail) };
          }
          if (report.status === "duplicate") {
            return { ...item, phase: "ready", detail: "Already in your sources" };
          }
          return { ...item, phase: "reading", documentId: report.document_id ?? null };
        })
      );
      onUploaded();
    } catch (err) {
      const message = err instanceof Error ? err.message : "Upload failed";
      setItems((prev) =>
        prev.map((item) =>
          tracked.some((t) => t.key === item.key)
            ? { ...item, phase: "failed", detail: message }
            : item
        )
      );
      onError(message);
    } finally {
      setBusy(false);
      if (fileInputRef.current) fileInputRef.current.value = "";
      if (folderInputRef.current) folderInputRef.current.value = "";
    }
  }

  async function retry(item: TrackedUpload) {
    if (item.documentId) {
      try {
        await api.reprocessDocument(item.documentId);
        setItems((prev) =>
          prev.map((row) =>
            row.key === item.key ? { ...row, phase: "reading", detail: null } : row
          )
        );
      } catch (err) {
        onError(err instanceof Error ? err.message : "Could not try again");
      }
      return;
    }
    setItems((prev) => prev.filter((row) => row.key !== item.key));
    await addFiles([item.file]);
  }

  function handleChange(event: ChangeEvent<HTMLInputElement>) {
    void addFiles(Array.from(event.target.files ?? []));
  }

  function handleDrop(event: DragEvent<HTMLDivElement>) {
    event.preventDefault();
    setDragging(false);
    void addFiles(Array.from(event.dataTransfer.files ?? []));
  }

  const inFlight = items.filter((i) => i.phase !== "ready").length;

  return (
    <div className="uploader">
      <div
        className={`drop-zone ${dragging ? "dragging" : ""}`}
        onDragOver={(e) => {
          e.preventDefault();
          setDragging(true);
        }}
        onDragLeave={() => setDragging(false)}
        onDrop={handleDrop}
      >
        <div style={{ display: "flex", justifyContent: "center", marginBottom: 10, color: "var(--primary)" }}>
          <UploadCloudIcon size={36} />
        </div>
        <p className="drop-hint">
          Drag & drop sources here, or choose a folder
        </p>
        <div style={{ display: "flex", justifyContent: "center", gap: 6, flexWrap: "wrap", marginBottom: 14 }}>
          {["PDF", "Word", "PowerPoint", "Excel", "Markdown", "Text"].map((ext) => (
            <span
              key={ext}
              style={{
                fontSize: "10px",
                fontFamily: "var(--font-mono)",
                padding: "2px 7px",
                borderRadius: "5px",
                background: "rgba(255, 255, 255, 0.05)",
                border: "1px solid var(--rule)",
                color: "var(--text-muted)",
              }}
            >
              {ext}
            </span>
          ))}
        </div>
        <div className="drop-actions">
          <button
            type="button"
            className="primary"
            disabled={busy}
            onClick={() => fileInputRef.current?.click()}
          >
            <UploadCloudIcon size={14} />
            <span>{busy ? "Adding…" : inFlight > 0 ? "Add more" : "Choose Files"}</span>
          </button>
          <button type="button" disabled={busy} onClick={() => folderInputRef.current?.click()}>
            <FolderIcon size={14} />
            <span>Add Folder</span>
          </button>
        </div>
      </div>

      <input
        ref={fileInputRef}
        type="file"
        accept={ACCEPT}
        multiple
        hidden
        onChange={handleChange}
      />
      <input ref={folderInputRef} type="file" multiple hidden onChange={handleChange} />

      {items.length > 0 && (
        <ul className="upload-queue">
          {items.map((item) => (
            <li key={item.key} className={`upload-item ${item.phase}`}>
              <span className="upload-name" title={item.filename}>
                {item.filename}
              </span>
              <span className="upload-phase">{PHASE_LABEL[item.phase]}</span>
              {item.detail && <span className="upload-detail">{item.detail}</span>}
              {item.phase === "failed" && (
                <button type="button" onClick={() => void retry(item)}>
                  Try again
                </button>
              )}
              {item.phase === "ready" && (
                <button
                  type="button"
                  className="link"
                  onClick={() => setItems((prev) => prev.filter((row) => row.key !== item.key))}
                >
                  Dismiss
                </button>
              )}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

/** Strip the exception class name the API puts in front of rejection details. */
function plainRejection(detail?: string | null): string {
  if (!detail) return "This file could not be read.";
  const stripped = detail.replace(/^[A-Za-z]+Error:\s*/, "").replace(/^[A-Za-z]+:\s*/, "");
  return stripped.charAt(0).toUpperCase() + stripped.slice(1);
}
