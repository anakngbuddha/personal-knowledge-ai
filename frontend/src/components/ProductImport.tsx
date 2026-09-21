import { useCallback, useEffect, useRef, useState } from "react";
import {
  catalogApi,
  type ImportPreviewOut,
  type ImportResultOut,
} from "../services/catalog";

/**
 * 3.3 "Import my product list".
 *
 * The product list starts empty, so this is the first thing a new user needs. Drop in
 * the spreadsheet the distributor sent, check what each column became, then add it. The
 * preview is the whole point: a mapping you cannot see is a mapping you cannot trust.
 */

const ACCEPT = ".csv,.tsv,.xlsx,.xlsm";

export function ProductImport({ onImported }: { onImported?: () => void }) {
  const [file, setFile] = useState<File | null>(null);
  const [preview, setPreview] = useState<ImportPreviewOut | null>(null);
  const [mapping, setMapping] = useState<Record<string, string>>({});
  const [overwrite, setOverwrite] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<ImportResultOut | null>(null);
  const [sampleAvailable, setSampleAvailable] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    catalogApi
      .sampleCatalogAvailable()
      .then((res) => setSampleAvailable(Boolean(res.available)))
      .catch(() => setSampleAvailable(false));
  }, []);

  const reset = useCallback(() => {
    setFile(null);
    setPreview(null);
    setMapping({});
    setResult(null);
    setError(null);
    if (inputRef.current) inputRef.current.value = "";
  }, []);

  const readFile = useCallback(async (chosen: File) => {
    setBusy(true);
    setError(null);
    setResult(null);
    try {
      const res = await catalogApi.previewProductList(chosen);
      setFile(chosen);
      setPreview(res);
      setMapping(res.mapping);
    } catch (e: any) {
      setError(e?.message ?? "That file could not be read.");
      setPreview(null);
    } finally {
      setBusy(false);
    }
  }, []);

  const runImport = useCallback(async () => {
    if (!file) return;
    setBusy(true);
    setError(null);
    try {
      const res = await catalogApi.importProductList(file, mapping, { overwrite });
      setResult(res);
      setPreview(null);
      setFile(null);
      if (inputRef.current) inputRef.current.value = "";
      onImported?.();
    } catch (e: any) {
      setError(e?.message ?? "The list could not be added.");
    } finally {
      setBusy(false);
    }
  }, [file, mapping, overwrite, onImported]);

  const loadSample = useCallback(async () => {
    setBusy(true);
    setError(null);
    try {
      await catalogApi.loadSampleCatalog();
      onImported?.();
    } catch (e: any) {
      setError(e?.message ?? "The sample list could not be loaded.");
    } finally {
      setBusy(false);
    }
  }, [onImported]);

  const namePicked = Object.values(mapping).includes("name");

  return (
    <section className="panel">
      <div className="panel-head">
        <div>
          <p className="kicker">My products</p>
          <h2>Import my product list</h2>
        </div>
        <div style={{ display: "flex", gap: "0.5rem", alignItems: "center" }}>
          <input
            ref={inputRef}
            type="file"
            accept={ACCEPT}
            disabled={busy}
            onChange={(e) => {
              const chosen = e.target.files?.[0];
              if (chosen) readFile(chosen);
            }}
          />
          {sampleAvailable && (
            <button type="button" disabled={busy} onClick={loadSample}>
              Load the sample list
            </button>
          )}
        </div>
      </div>

      {!preview && !result && (
        <p className="muted">
          Drop in the spreadsheet your distributor sent (CSV or Excel). One row per product,
          column titles in the first row. You will see what each column becomes before anything
          is added.
        </p>
      )}

      {error && <div className="banner error">{error}</div>}
      {busy && <p className="muted">Working…</p>}

      {preview && (
        <>
          <p className="muted">
            {preview.row_count} rows read
            {preview.sheet_name ? ` from ${preview.sheet_name}` : ""}. {preview.ready} ready to add.
            {preview.truncated ? " Only the first part of the file was read." : ""}
          </p>

          <div className="import-mapping" style={{ display: "grid", gap: "0.6rem" }}>
            {preview.headers.map((header, index) => {
              const key = String(index);
              const sample = preview.sample_rows
                .map((row) => row[index])
                .filter((value) => value)
                .slice(0, 2)
                .join(" · ");
              return (
                <div
                  key={key}
                  style={{
                    display: "grid",
                    gridTemplateColumns: "minmax(8rem, 1fr) minmax(9rem, 1fr) 2fr",
                    gap: "0.6rem",
                    alignItems: "center",
                  }}
                >
                  <strong>{header || `Column ${index + 1}`}</strong>
                  <select
                    value={mapping[key] ?? ""}
                    onChange={(e) => setMapping((prev) => ({ ...prev, [key]: e.target.value }))}
                  >
                    <option value="">Leave this out</option>
                    {preview.fields.map((f) => (
                      <option key={f.key} value={f.key}>
                        {f.label}
                        {f.required ? " (needed)" : ""}
                      </option>
                    ))}
                  </select>
                  <span className="muted">{sample}</span>
                </div>
              );
            })}
          </div>

          {!namePicked && (
            <div className="banner error">
              Pick the column that holds the product name. Everything else is optional.
            </div>
          )}

          {preview.problems.length > 0 && (
            <ul className="muted">
              {preview.problems.slice(0, 8).map((problem, i) => (
                <li key={i}>
                  {problem.row > 0 ? `Row ${problem.row}: ` : ""}
                  {problem.reason}
                </li>
              ))}
            </ul>
          )}

          <div
            style={{
              display: "flex",
              gap: "0.75rem",
              alignItems: "center",
              marginTop: "0.75rem",
            }}
          >
            <button
              className="primary"
              type="button"
              disabled={busy || !namePicked}
              onClick={runImport}
            >
              Add {preview.ready} products
            </button>
            <button type="button" disabled={busy} onClick={reset}>
              Cancel
            </button>
            <label
              className="muted"
              style={{ display: "flex", gap: "0.35rem", alignItems: "center" }}
            >
              <input
                type="checkbox"
                checked={overwrite}
                onChange={(e) => setOverwrite(e.target.checked)}
              />
              Replace what I already have
            </label>
          </div>
        </>
      )}

      {result && (
        <div className="banner">
          <strong>
            {result.created} added, {result.updated} filled in, {result.unchanged} already right.
          </strong>
          {result.problems.length > 0 && (
            <ul className="muted">
              {result.problems.slice(0, 8).map((problem, i) => (
                <li key={i}>
                  {problem.row > 0 ? `Row ${problem.row}: ` : ""}
                  {problem.reason}
                </li>
              ))}
            </ul>
          )}
        </div>
      )}
    </section>
  );
}
