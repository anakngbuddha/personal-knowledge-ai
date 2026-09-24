import { useEffect, useState } from "react";
import { api } from "../services/api";
import type { NotebookRecord } from "../types";

interface Props {
  notebookId: string | null;
  onChange: (id: string | null) => void;
}

export function NotebookPicker({ notebookId, onChange }: Props) {
  const [notebooks, setNotebooks] = useState<NotebookRecord[]>([]);
  const [name, setName] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [confirmDelete, setConfirmDelete] = useState(false);

  async function refresh(selectId?: string | null) {
    const listed = await api.listNotebooks();
    setNotebooks(listed.notebooks);
    const next = selectId ?? notebookId;
    if (next && listed.notebooks.some((row) => row.id === next)) onChange(next);
    else onChange(listed.notebooks[0]?.id ?? null);
  }

  useEffect(() => {
    void refresh().catch((err: unknown) => {
      setError(err instanceof Error ? err.message : "Could not load notebooks");
    });
    // Load once. The parent owns the selected id after that.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  async function create() {
    const trimmed = name.trim();
    if (!trimmed) return;
    setError(null);
    try {
      const created = await api.createNotebook(trimmed);
      setName("");
      await refresh(created.id);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not create the notebook");
    }
  }

  async function rename() {
    if (!notebookId) return;
    const trimmed = window.prompt("Notebook name", notebooks.find((row) => row.id === notebookId)?.name ?? "");
    if (!trimmed?.trim()) return;
    setError(null);
    try {
      await api.renameNotebook(notebookId, trimmed.trim());
      await refresh(notebookId);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not rename the notebook");
    }
  }

  async function remove() {
    if (!notebookId) return;
    setError(null);
    try {
      await api.deleteNotebook(notebookId);
      await refresh(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not delete the notebook");
    }
  }

  return (
    <div className="notebook-picker">
      <div className="notebook-header-row">
        <span className="notebook-title">Notebook</span>
        <span className="notebook-deals-badge">0 Deals Selected</span>
      </div>
      <div className="notebook-select-wrap">
        <select
          className="notebook-select"
          value={notebookId ?? ""}
          onChange={(e) => onChange(e.target.value || null)}
        >
          {notebooks.length === 0 && <option value="">No notebook yet</option>}
          {notebooks.map((row) => (
            <option key={row.id} value={row.id}>
              {row.name}
            </option>
          ))}
        </select>
        <span className="notebook-select-chevron">▾</span>
      </div>
      <div className="notebook-input-wrap">
        <input
          className="notebook-input"
          value={name}
          onChange={(e) => setName(e.target.value)}
          placeholder="New deal or customer"
          maxLength={120}
        />
      </div>
      <div className="notebook-links-row">
        <button
          type="button"
          className="notebook-link-create"
          onClick={() => void create()}
          disabled={!name.trim()}
        >
          Create
        </button>
        <button
          type="button"
          className="notebook-link-btn"
          onClick={() => void rename()}
          disabled={!notebookId}
        >
          Rename
        </button>
        <button
          type="button"
          className="notebook-link-btn"
          disabled={!notebookId}
          onClick={() => {
            if (!confirmDelete) {
              setConfirmDelete(true);
              return;
            }
            setConfirmDelete(false);
            void remove();
          }}
          onBlur={() => setConfirmDelete(false)}
        >
          {confirmDelete ? "Confirm" : "Delete"}
        </button>
      </div>
      {error && <p className="insight-problem">{error}</p>}
    </div>
  );
}
