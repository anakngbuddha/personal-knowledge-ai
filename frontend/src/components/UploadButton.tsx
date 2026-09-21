import { useRef, useState } from "react";

import { api } from "../services/api";

interface Props {
  onUploaded: () => void;
  onError: (message: string) => void;
}

export function UploadButton({ onUploaded, onError }: Props) {
  const inputRef = useRef<HTMLInputElement>(null);
  const [uploading, setUploading] = useState(false);

  async function handleChange(event: React.ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0];
    if (!file) return;
    setUploading(true);
    try {
      const res = await api.uploadDocument(file);
      if (res.rejected > 0) {
        const firstRejection = res.results.find((r) => r.status === "rejected");
        onError(firstRejection?.detail || "Document upload rejected");
      } else if (res.duplicates > 0) {
        onError("An identical document has already been ingested.");
      }
      onUploaded();
    } catch (err) {
      onError(err instanceof Error ? err.message : "Upload failed");
    } finally {
      setUploading(false);
      if (inputRef.current) inputRef.current.value = "";
    }
  }

  return (
    <>
      <button type="button" className="primary" disabled={uploading} onClick={() => inputRef.current?.click()}>
        {uploading ? "Filing…" : "File document"}
      </button>
      <input
        ref={inputRef}
        type="file"
        accept=".pdf,.docx,.pptx,.xlsx,.txt,.md,.html"
        hidden
        onChange={handleChange}
      />
    </>
  );
}
