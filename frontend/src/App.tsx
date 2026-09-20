import { useState } from "react";

import { ChunkInspector } from "./components/ChunkInspector";
import { DocumentList } from "./components/DocumentList";
import { GraphExplorer } from "./components/GraphExplorer";
import { GroundedChat } from "./components/GroundedChat";
import { SearchExplorer } from "./components/SearchExplorer";
import { UploadButton } from "./components/UploadButton";
import { useDocuments } from "./hooks/useDocuments";

export default function App() {
  const [activeTab, setActiveTab] = useState<"documents" | "search" | "chat" | "graph">("graph");
  const { documents, loading, error, refresh, setError } = useDocuments();
  const [selectedId, setSelectedId] = useState<string | null>(null);

  return (
    <div className="app">
      <header className="topbar">
        <div className="brand">
          <h1>Solution Engineering Knowledge Workspace</h1>
          <span className="phase">Phases 1–4 Complete · Ingestion, Hybrid Retrieval, Grounded Chat &amp; Product Graph</span>
        </div>
        <nav className="nav-tabs">
          <button
            className={`tab-btn ${activeTab === "graph" ? "active" : ""}`}
            onClick={() => setActiveTab("graph")}
          >
            Product Graph (P4)
          </button>
          <button
            className={`tab-btn ${activeTab === "chat" ? "active" : ""}`}
            onClick={() => setActiveTab("chat")}
          >
            Grounded Chat (P3)
          </button>
          <button
            className={`tab-btn ${activeTab === "search" ? "active" : ""}`}
            onClick={() => setActiveTab("search")}
          >
            Hybrid Search (P2)
          </button>
          <button
            className={`tab-btn ${activeTab === "documents" ? "active" : ""}`}
            onClick={() => setActiveTab("documents")}
          >
            Documents (P1)
          </button>
        </nav>
      </header>

      {error && <div className="banner error">{error}</div>}

      <main className="content-container">
        {activeTab === "graph" && <GraphExplorer />}

        {activeTab === "chat" && <GroundedChat />}

        {activeTab === "search" && <SearchExplorer />}

        {activeTab === "documents" && (
          <div className="layout">
            <section className="panel documents">
              <div className="panel-head">
                <h2>Documents ({documents.length})</h2>
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
                <h2>Chunks &amp; Metadata</h2>
              </div>
              <ChunkInspector documentId={selectedId} />
            </section>
          </div>
        )}
      </main>
    </div>
  );
}

