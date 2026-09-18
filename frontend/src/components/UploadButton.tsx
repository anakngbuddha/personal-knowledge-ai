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
      await api.uploadDocument(file);
      onUploaded();
    } catch (err) {
      onError(err instanceof Error ? err.message : "upload failed");
    } finally {
      setUploading(false);
      if (inputRef.current) inputRef.current.value = "";
    }
  }

  return (
    <>
      <button className="primary" disabled={uploading} onClick={() => inputRef.current?.click()}>
        {uploading ? "Uploading..." : "+ Upload"}
      </button>
      <input
        ref={inputRef}
        type="file"
        accept=".pdf,.txt,.docx"
        hidden
        onChange={handleChange}
      />
    </>
  );
}
