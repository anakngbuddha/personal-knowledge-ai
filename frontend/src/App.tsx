import { useState } from "react";

import { ChunkInspector } from "./components/ChunkInspector";
import { DocumentList } from "./components/DocumentList";
import { UploadButton } from "./components/UploadButton";
import { useDocuments } from "./hooks/useDocuments";

export default function App() {
  const { documents, loading, error, refresh, setError } = useDocuments();
  const [selectedId, setSelectedId] = useState<string | null>(null);

  return (
    <div className="app">
      <header className="topbar">
        <h1>Personal Knowledge AI</h1>
        <span className="phase">V1 · Phase 1: ingestion</span>
      </header>

      {error && <div className="banner error">{error}</div>}

      <main className="layout">
        <section className="panel documents">
          <div className="panel-head">
            <h2>Documents</h2>
            <UploadButton onUploaded={refresh} onError={setError} />
          </div>
          <DocumentList
            documents={documents}
            loading={loading}
            selectedId={selectedId}
            onSelect={setSelectedId}
            onChanged={refresh}
            onError={setError}
          />
        </section>

        <section className="panel workspace">
          <div className="panel-head">
            <h2>Chunks &amp; metadata</h2>
          </div>
          <ChunkInspector documentId={selectedId} />
          <footer className="deferred">
            Grounded chat with citations arrives in Phase 3. Retrieval (Phase 2) comes first.
          </footer>
        </section>
      </main>
    </div>
  );
}
