import { useEffect, useState } from "react";
import { AuthScreen } from "./components/AuthScreen";
import { ChunkInspector } from "./components/ChunkInspector";
import { DocumentList } from "./components/DocumentList";
import { GraphExplorer } from "./components/GraphExplorer";
import { GroundedChat } from "./components/GroundedChat";
import { IntegrationsPanel } from "./components/IntegrationsPanel";
import { MapEditor } from "./components/MapEditor";
import { NotesPanel } from "./components/NotesPanel";
import { OpsPanel } from "./components/OpsPanel";
import { ProductImport } from "./components/ProductImport";
import { SearchExplorer } from "./components/SearchExplorer";
import { SettingsPanel } from "./components/SettingsPanel";
import { SourceInsightCard } from "./components/SourceInsightCard";
import { UploadButton } from "./components/UploadButton";
import { useDocuments } from "./hooks/useDocuments";
import { usePrincipal } from "./hooks/useWorkflows";
import { apiPointsAtLocalhostFromRemote, getAccessToken, onServerWake, setAccessToken } from "./services/http";
import { SERVER_WAKING } from "./services/errors";

type Tab = "sources" | "ask" | "notes" | "map" | "connections" | "settings";

const TABS: { id: Tab; name: string }[] = [
  { id: "ask", name: "Ask" },
  { id: "notes", name: "Notes" },
  { id: "sources", name: "Sources" },
  { id: "connections", name: "Connectors" },
  { id: "map", name: "Map" },
  { id: "settings", name: "Settings" },
];

export default function App() {
  const [authenticated, setAuthenticated] = useState(Boolean(getAccessToken()));
  const [activeTab, setActiveTab] = useState<Tab>("ask");
  const { documents, loading, error, refresh, setError } = useDocuments(authenticated);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [mapVersion, setMapVersion] = useState(0);
  const [waking, setWaking] = useState(false);
  const principal = usePrincipal();

  useEffect(() => {
    if (!getAccessToken()) setAuthenticated(false);
  }, []);

  useEffect(() => {
    const stop = onServerWake((phase) => setWaking(phase === "waking"));
    return () => {
      stop();
    };
  }, []);

  function signOut() {
    setAccessToken(null);
    setAuthenticated(false);
  }

  if (!authenticated) return <AuthScreen onAuthenticated={() => setAuthenticated(true)} />;

  return (
    <div className="app">
      <header className="masthead">
        <div className="brand">
          <span className="brand-kicker">Solutions engineering</span>
          <h1>Field Desk</h1>
        </div>
        <div className="mast-meta">
          <button className="link-button" onClick={signOut}>
            Sign out
          </button>
        </div>
      </header>
      <div className="desk">
        <nav className="field-index" aria-label="Main">
          {TABS.map((tab) => (
            <button
              key={tab.id}
              type="button"
              className={`index-item word ${activeTab === tab.id ? "active" : ""}`}
              onClick={() => setActiveTab(tab.id)}
            >
              <span className="index-name">{tab.name}</span>
            </button>
          ))}
        </nav>
        <div className="desk-body">
          {waking && <div className="banner info">{SERVER_WAKING}</div>}
          {apiPointsAtLocalhostFromRemote() && (
            <div className="banner error">
              This build is not pointed at the server. Set the API address and redeploy.
            </div>
          )}
          {error && activeTab === "sources" && <div className="banner error">{error}</div>}
          <main className="content-container">
            {activeTab === "ask" && (
              <GroundedChat
                sourceCount={documents.length}
                onNavigate={(tab) => setActiveTab(tab === "map" ? "map" : "sources")}
              />
            )}
            {activeTab === "connections" && <IntegrationsPanel />}
            {activeTab === "map" && (
              <div className="map-stage">
                <GraphExplorer key={mapVersion} />
                <div className="map-float">
                  <ProductImport onImported={() => setMapVersion((v) => v + 1)} />
                  <details className="map-edit">
                    <summary>Edit the map</summary>
                    <MapEditor onChanged={() => setMapVersion((v) => v + 1)} />
                  </details>
                </div>
              </div>
            )}
            {activeTab === "notes" && <NotesPanel />}
            {activeTab === "settings" && <SettingsPanel principal={principal} onSignOut={signOut} />}
            {activeTab === "sources" && (
              <div className="sources-page">
                <div className="layout">
                  <section className="panel documents">
                    <div className="panel-head">
                      <div>
                        <h2>Sources ({documents.length})</h2>
                      </div>
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
                      <div>
                        <h2>{selectedId ? "What this source says" : "Pick a source"}</h2>
                      </div>
                    </div>
                    {selectedId ? (
                      <>
                        <SourceInsightCard documentId={selectedId} onChanged={refresh} />
                        <ChunkInspector documentId={selectedId} />
                      </>
                    ) : (
                      <p className="muted">Pick a source on the left to see what it says.</p>
                    )}
                  </section>
                </div>
                <SearchExplorer />
                <OpsPanel mode="watches" />
              </div>
            )}
          </main>
        </div>
      </div>
    </div>
  );
}
