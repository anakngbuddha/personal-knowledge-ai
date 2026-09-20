import { useState } from "react";

import { ChunkInspector } from "./components/ChunkInspector";
import { DocumentList } from "./components/DocumentList";
import { GraphExplorer } from "./components/GraphExplorer";
import { GroundedChat } from "./components/GroundedChat";
import { SearchExplorer } from "./components/SearchExplorer";
import { UploadButton } from "./components/UploadButton";
import { WorkflowWorkspace } from "./components/WorkflowWorkspace";
import { useDocuments } from "./hooks/useDocuments";
import { apiPointsAtLocalhostFromRemote } from "./services/http";

export default function App() {
  const [activeTab, setActiveTab] = useState<"documents" | "search" | "chat" | "graph" | "workflows">(
    "workflows"
  );
  const { documents, loading, error, refresh, setError } = useDocuments();
  const [selectedId, setSelectedId] = useState<string | null>(null);

  return (
    <div className="app">
      <header className="topbar">
        <div className="brand">
          <h1>Solution Engineering Knowledge Workspace</h1>
          <span className="phase">Phase 7 · Workflow cockpit, HITL review &amp; deliverable download</span>
        </div>
        <nav className="nav-tabs">
          <button
            className={`tab-btn ${activeTab === "workflows" ? "active" : ""}`}
            onClick={() => setActiveTab("workflows")}
          >
            Workflows (P7)
          </button>
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

      {apiPointsAtLocalhostFromRemote() && (
        <div className="banner error">
          This Vercel build is not pointed at Render. Set{" "}
          <code>VITE_API_BASE_URL</code> to your Render URL (no trailing slash),
          redeploy the frontend, and set <code>CORS_ORIGINS</code> on Render to{" "}
          <code>{typeof window !== "undefined" ? window.location.origin : "https://your-app.vercel.app"}</code>
          . Shortcut: add <code>?api=https://&lt;service&gt;.onrender.com</code> to this URL once.
        </div>
      )}
      {error && activeTab === "documents" && <div className="banner error">{error}</div>}

      <main className="content-container">
        {activeTab === "workflows" && <WorkflowWorkspace />}

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
