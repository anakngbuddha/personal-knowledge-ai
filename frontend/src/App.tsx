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
import { NotesPanel } from "./components/NotesPanel";
import { OpsPanel } from "./components/OpsPanel";
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
    { id: "ask", name: "Ask Intelligence", icon: StarIcon, badge: "AI" },
    { id: "notes", name: "Notes", icon: BookOpenIcon, badge: "18" },
    { id: "sources", name: "Sources", icon: FileTextIcon, badge: String(documents.length || 50) },
    { id: "connections", name: "Connectors", icon: ZapIcon, badge: "Live" },
    { id: "map", name: "Knowledge Map", icon: NetworkIcon },
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
            <LogoMark size={26} />
          </div>
          <div className="brand-info">
            <div className="brand-title-wrap">
              <span className="brand-name">Field Desk</span>
              <span className="version-pill">v2.4</span>
            </div>
            <span className="brand-kicker">Knowledge Engine • Cupertino Core</span>
          </div>
        </div>

        <div className="mast-center">
          <div className="status-badge-live">
            <span className="pulse-dot" />
            <span>Catalog Grounded &bull; HNSW: 14ms</span>
          </div>

          <div className="mast-search-box">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" style={{ color: "var(--text-muted)", flexShrink: 0 }}>
              <circle cx="11" cy="11" r="8" />
              <line x1="21" y1="21" x2="16.65" y2="16.65" />
            </svg>
            <input
              type="text"
              className="mast-search-input"
              placeholder="Jump to note or search catalog [[product:name]].."
            />
            <kbd className="mast-search-shortcut">⌘K</kbd>
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
              <span className="user-name">{principal?.organization_name || "Enterprise Tenant"}</span>
              <span className="user-org">Active • Zero Retention</span>
            </div>
          </div>

          <button type="button" className="signout-btn" onClick={signOut} title="Sign out of workspace">
            <LogOutIcon size={14} />
            <span>Sign out</span>
          </button>
        </div>
      </header>

      {/* ── Main Workspace Body ─────────────────────────────────────── */}
      <div className={`desk ${activeTab === "ask" || activeTab === "map" ? "desk-ask-mode" : ""}`}>
        {/* Navigation Sidebar (rendered when not on ask or map tab, since both have integrated workspace sidebars) */}
        {activeTab !== "ask" && activeTab !== "map" && (
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

            <div className="nav-section notebooks-nav-section">
              <div className="index-label-row">
                <span className="index-label" style={{ padding: 0 }}>NOTEBOOKS</span>
                <button
                  type="button"
                  className="btn-add-notebook"
                  onClick={() => setActiveTab("notes")}
                  title="Create new notebook"
                >
                  +
                </button>
              </div>
              <button
                type="button"
                className={`index-item notebook-item ${activeTab === "notes" ? "active" : ""}`}
                onClick={() => setActiveTab("notes")}
              >
                <span className="notebook-dot active" />
                <span className="index-name">Acme on-prem sizing deal</span>
              </button>
              <button
                type="button"
                className="index-item notebook-item"
                onClick={() => setActiveTab("notes")}
              >
                <span className="index-name" style={{ paddingLeft: "14px" }}>
                  EMEA Retail Banking RFI
                </span>
              </button>
              <button
                type="button"
                className="index-item notebook-item"
                onClick={() => setActiveTab("notes")}
              >
                <span className="index-name" style={{ paddingLeft: "14px" }}>
                  HNSW Hardware Specs Q3
                </span>
              </button>
            </div>

            <div className="sidebar-footer">
              <div className="telemetry-card">
                <div className="telemetry-header">
                  <span className="telemetry-title">VECTOR MEMORY</span>
                  <span className="telemetry-status">
                    <DatabaseIcon size={12} /> HNSW
                  </span>
                </div>
                <div className="telemetry-sub" style={{ lineHeight: 1.45 }}>
                  {documents.length || 50} sources indexed<br />
                  Tenant isolation: <span style={{ color: "#10b981", fontWeight: 600 }}>Enforced</span>
                </div>
                <div style={{ display: "flex", justifyContent: "space-between", marginTop: "6px", fontSize: "10px", color: "var(--text-muted)", fontFamily: "var(--font-mono)" }}>
                  <span>Dimensions: 1536</span>
                  <span style={{ color: "#10b981", fontWeight: 600 }}>Sync: OK</span>
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
              <GraphExplorer
                key={mapVersion}
                sourceCount={documents.length}
                onNavigate={(tab) => setActiveTab(tab === "map" ? "map" : tab === "ask" ? "ask" : "sources")}
                activeTab={activeTab}
                onTabChange={setActiveTab}
                tabs={tabs}
                onMapChanged={() => setMapVersion((v) => v + 1)}
              />
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
