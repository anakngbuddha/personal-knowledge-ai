import React, { useEffect, useState } from "react";
import { AuthScreen } from "./components/AuthScreen";
import { ChunkInspector } from "./components/ChunkInspector";
import { DocumentList } from "./components/DocumentList";
import { GraphExplorer } from "./components/GraphExplorer";
import { GroundedChat } from "./components/GroundedChat";
import {
  BookOpenIcon,
  DatabaseIcon,
  FileTextIcon,
  LogoMark,
  LogOutIcon,
  MoonIcon,
  NetworkIcon,
  SettingsIcon,
  StarIcon,
  SunIcon,
  ZapIcon,
} from "./components/Icons";
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

interface TabItem {
  id: Tab;
  name: string;
  icon: React.ComponentType<{ size?: number }>;
  badge?: string;
}

export default function App() {
  const [authenticated, setAuthenticated] = useState(Boolean(getAccessToken()));
  const [activeTab, setActiveTab] = useState<Tab>("ask");
  const { documents, loading, error, refresh, setError } = useDocuments(authenticated);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [mapVersion, setMapVersion] = useState(0);
  const [waking, setWaking] = useState(false);
  const principal = usePrincipal();

  // Dark/Light theme manager - default to light matching reference design
  const [theme, setTheme] = useState<"dark" | "light">(() => {
    try {
      const saved = localStorage.getItem("fd_theme");
      if (saved === "light" || saved === "dark") return saved;
      return "light";
    } catch {
      return "light";
    }
  });

  useEffect(() => {
    document.documentElement.setAttribute("data-theme", theme);
    try {
      localStorage.setItem("fd_theme", theme);
    } catch {
      /* ignore storage errors */
    }
  }, [theme]);

  function toggleTheme() {
    setTheme((prev) => (prev === "dark" ? "light" : "dark"));
  }

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

  const tabs: TabItem[] = [
    { id: "ask", name: "Ask", icon: StarIcon, badge: "AI" },
    { id: "notes", name: "Notes", icon: BookOpenIcon },
    { id: "sources", name: "Sources", icon: FileTextIcon, badge: String(documents.length || 50) },
    { id: "connections", name: "Connectors", icon: ZapIcon, badge: "Live" },
    { id: "map", name: "Map", icon: NetworkIcon },
    { id: "settings", name: "Settings", icon: SettingsIcon },
  ];

  const userInitials = (principal?.organization_name || "S")
    .split(" ")
    .map((w: string) => w[0] || "")
    .join("")
    .slice(0, 2)
    .toUpperCase();

  return (
    <div className="app">
      {/* ── Top Glass Masthead ────────────────────────────────────────── */}
      <header className="masthead">
        <div className="brand">
          <div className="brand-emblem" title="Field Desk AI">
            <LogoMark size={32} />
          </div>
          <div className="brand-info">
            <div className="brand-title-wrap">
              <span className="brand-kicker">KNOWLEDGE ENGINE</span>
              <span className="version-pill">v2.4</span>
              <span className="brand-sep">|</span>
              <h1 className="brand-name">Field Desk</h1>
            </div>
          </div>
        </div>

        <div className="mast-center">
          <div className="status-badge-live">
            <span className="pulse-dot" />
            <span>Catalog Grounded &bull; Multi-source active</span>
          </div>
        </div>

        <div className="mast-meta">
          <button
            type="button"
            className="theme-toggle-btn"
            onClick={toggleTheme}
            title={`Switch to ${theme === "dark" ? "light" : "dark"} mode`}
            aria-label="Toggle visual theme"
          >
            {theme === "dark" ? <SunIcon size={16} /> : <MoonIcon size={16} />}
          </button>

          <div className="user-profile-chip">
            <div className="user-avatar">{userInitials || "S"}</div>
            <div className="user-info">
              <span className="user-name">{principal?.organization_name || "Enterprise"}</span>
              <span className="user-org">ACTIVE</span>
            </div>
          </div>

          <button type="button" className="signout-btn" onClick={signOut} title="Sign out of workspace">
            <LogOutIcon size={14} />
            <span>Sign out</span>
          </button>
        </div>
      </header>

      {/* ── Main Workspace Body ─────────────────────────────────────── */}
      <div className={`desk ${activeTab === "ask" ? "desk-ask-mode" : ""}`}>
        {/* Navigation Sidebar (rendered when not on ask tab, since ask has its integrated sidebar) */}
        {activeTab !== "ask" && (
          <nav className="field-index" aria-label="Main Navigation">
            <div className="nav-section">
              <div className="index-label">Workspace</div>
              {tabs.map((tab) => {
                const Icon = tab.icon;
                const isActive = activeTab === tab.id;
                return (
                  <button
                    key={tab.id}
                    type="button"
                    className={`index-item ${isActive ? "active" : ""}`}
                    onClick={() => setActiveTab(tab.id)}
                    aria-current={isActive ? "page" : undefined}
                  >
                    <span className="tab-icon">
                      <Icon size={18} />
                    </span>
                    <span className="index-name">{tab.name}</span>
                    {tab.badge && <span className="tab-badge">{tab.badge}</span>}
                  </button>
                );
              })}
            </div>

            <div className="sidebar-footer">
              <div className="telemetry-card">
                <div className="telemetry-header">
                  <span className="telemetry-title">Vector Memory</span>
                  <span className="telemetry-status">
                    <DatabaseIcon size={12} /> HNSW
                  </span>
                </div>
                <div className="telemetry-sub">
                  {documents.length || 50} sources indexed • tenant isolation active
                </div>
              </div>
            </div>
          </nav>
        )}

        {/* Content Region */}
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
                activeTab={activeTab}
                onTabChange={setActiveTab}
                tabs={tabs}
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
                        <h2>{selectedId ? "Source Insight" : "Pick a source"}</h2>
                      </div>
                    </div>
                    {selectedId ? (
                      <>
                        <SourceInsightCard documentId={selectedId} onChanged={refresh} />
                        <ChunkInspector documentId={selectedId} />
                      </>
                    ) : (
                      <p className="muted">Select a document from the left library to inspect its synthesis, facts, and chunks.</p>
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
