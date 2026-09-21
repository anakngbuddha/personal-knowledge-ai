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
  const [activeTab, setActiveTab] = useState<"documents" | "search" | "chat" | "graph" | "workflows">("workflows");
  const { documents, loading, error, refresh, setError } = useDocuments();
  const [selectedId, setSelectedId] = useState<string | null>(null);
  return <div className="app">
    <header className="topbar"><div className="brand"><h1>Solution Engineering Knowledge Workspace</h1><span className="phase">Phase 8 · HLD/BOM, incident triage &amp; upgrade impact</span></div><nav className="nav-tabs">
      {(["workflows", "graph", "chat", "search", "documents"] as const).map((tab) => <button key={tab} className={`tab-btn ${activeTab === tab ? "active" : ""}`} onClick={() => setActiveTab(tab)}>{tab === "workflows" ? "Workflows (P8)" : tab === "graph" ? "Product Graph (P4)" : tab === "chat" ? "Grounded Chat (P3)" : tab === "search" ? "Hybrid Search (P2)" : "Documents (P1)"}</button>)}
    </nav></header>
    {apiPointsAtLocalhostFromRemote() && <div className="banner error">This build is not pointed at the backend. Set <code>VITE_API_BASE_URL</code> and <code>CORS_ORIGINS</code>, then redeploy.</div>}
    {error && activeTab === "documents" && <div className="banner error">{error}</div>}
    <main className="content-container">
      {activeTab === "workflows" && <WorkflowWorkspace />}{activeTab === "graph" && <GraphExplorer />}{activeTab === "chat" && <GroundedChat />}{activeTab === "search" && <SearchExplorer />}
      {activeTab === "documents" && <div className="layout"><section className="panel documents"><div className="panel-head"><h2>Documents ({documents.length})</h2><UploadButton onUploaded={refresh} onError={setError} /></div><DocumentList documents={documents} loading={loading} selectedId={selectedId} onSelect={setSelectedId} onChanged={refresh} onError={setError} /></section><section className="panel workspace"><div className="panel-head"><h2>Chunks &amp; Metadata</h2></div><ChunkInspector documentId={selectedId} /></section></div>}
    </main>
  </div>;
}
