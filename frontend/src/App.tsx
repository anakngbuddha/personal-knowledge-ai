import React, { useEffect, useState } from "react";
import { AuthScreen } from "./components/AuthScreen";
import { GraphExplorer } from "./components/GraphExplorer";
import { GroundedChat } from "./components/GroundedChat";
import { LandingPage } from "./components/LandingPage";
import { SeaBubbles } from "./components/SeaBubbles";
import {
  BellIcon,
  BookOpenIcon,
  ChevronDownIcon,
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
import { SettingsPanel } from "./components/SettingsPanel";
import { SourcesWorkspace } from "./components/SourcesWorkspace";
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
  const [showAuth, setShowAuth] = useState(false);
  const [activeTab, setActiveTab] = useState<Tab>("ask");
  const { documents, loading, error, refresh, setError } = useDocuments(authenticated);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [seedQuestion, setSeedQuestion] = useState<string | null>(null);
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

  if (!authenticated) {
    if (showAuth) {
      return (
        <AuthScreen
          onAuthenticated={() => {
            setAuthenticated(true);
            setShowAuth(false);
          }}
          onBack={() => setShowAuth(false)}
        />
      );
    }
    return <LandingPage onLogin={() => setShowAuth(true)} />;
  }

  const tabs: TabItem[] = [
    { id: "ask", name: "Ask Intelligence", icon: StarIcon, badge: "AI" },
    { id: "notes", name: "Notes", icon: BookOpenIcon, badge: "18" },
    { id: "sources", name: "Sources", icon: FileTextIcon, badge: String(documents.length || 50) },
    { id: "connections", name: "Connectors", icon: ZapIcon, badge: "11 ●" },
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
      <SeaBubbles count={14} variant="dashboard" className="app-ambient-bubbles" />
      {/* ── Top Glass Masthead ────────────────────────────────────────── */}
      <header className="masthead">
        <div className="brand">
          <div className="brand-emblem" title="Deep Atlas AI">
            <LogoMark size={28} />
          </div>
          <div className="brand-info">
            <div className="brand-title-wrap">
              <span className="brand-name">Deep Atlas</span>
              <span className="version-pill">v2.4</span>
            </div>
            <span className="brand-kicker">AUTONOMOUS KNOWLEDGE ENGINE &bull; ENTERPRISE CORE</span>
          </div>
        </div>

        <div className="mast-center">
          <div className="status-badge-live">
            <span className="pulse-dot" />
            <span>Catalogs Grounded &bull; HNSW &bull; 14ms</span>
          </div>

          <div className="mast-search-box">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" style={{ color: "var(--text-muted)", flexShrink: 0 }}>
              <circle cx="11" cy="11" r="8" />
              <line x1="21" y1="21" x2="16.65" y2="16.65" />
            </svg>
            <input
              type="text"
              className="mast-search-input"
              placeholder="Jump to note or search catalog | product..."
            />
            <kbd className="mast-search-shortcut">⌘ K</kbd>
          </div>
        </div>

        <div className="mast-meta">
          <button
            type="button"
            className="mast-bell-btn"
            title="Notifications"
            aria-label="Notifications"
          >
            <BellIcon size={16} />
            <span className="bell-badge-dot" />
          </button>

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
              <span className="user-name">Enterprise Tenant</span>
              <span className="user-org">Deep Atlas – Enterprise</span>
            </div>
            <ChevronDownIcon size={12} className="user-chevron" />
          </div>

          <button type="button" className="signout-btn" onClick={signOut} title="Sign out of workspace">
            <LogOutIcon size={14} />
            <span>Sign out</span>
          </button>
        </div>
      </header>

      {/* ── Main Workspace Body ─────────────────────────────────────── */}
      <div className={`desk ${activeTab === "ask" || activeTab === "map" || activeTab === "sources" ? "desk-ask-mode" : ""}`}>
        {/* Navigation Sidebar (rendered when not on ask, map, or sources tab, since all three have integrated workspace sidebars) */}
        {activeTab !== "ask" && activeTab !== "map" && activeTab !== "sources" && (
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
          {error && activeTab !== "sources" && <div className="banner error">{error}</div>}
          
          <main className="content-container">
            {activeTab === "ask" && (
              <GroundedChat
                sourceCount={documents.length}
                onNavigate={(tab) => {
                  setActiveTab(tab === "map" ? "map" : "sources");
                  setSeedQuestion(null);
                }}
                activeTab={activeTab}
                onTabChange={(t) => {
                  setActiveTab(t);
                  setSeedQuestion(null);
                }}
                tabs={tabs}
                initialQuestion={seedQuestion}
              />
            )}
            {activeTab === "connections" && <IntegrationsPanel />}
            {activeTab === "map" && (
              <GraphExplorer
                key={mapVersion}
                sourceCount={documents.length}
                onNavigate={(tab) => {
                  setActiveTab(tab === "map" ? "map" : tab === "ask" ? "ask" : "sources");
                  setSeedQuestion(null);
                }}
                activeTab={activeTab}
                onTabChange={(t) => {
                  setActiveTab(t);
                  setSeedQuestion(null);
                }}
                tabs={tabs}
                onMapChanged={() => setMapVersion((v) => v + 1)}
              />
            )}
            {activeTab === "notes" && <NotesPanel />}
            {activeTab === "settings" && <SettingsPanel principal={principal} onSignOut={signOut} />}
            {activeTab === "sources" && (
              <SourcesWorkspace
                documents={documents}
                loading={loading}
                error={error}
                refresh={refresh}
                setError={setError}
                selectedId={selectedId}
                onSelect={setSelectedId}
                onNavigate={(tab, prompt) => {
                  if (prompt) setSeedQuestion(prompt);
                  setActiveTab(tab);
                }}
                activeTab={activeTab}
                onTabChange={(t) => {
                  setActiveTab(t);
                  setSeedQuestion(null);
                }}
                tabs={tabs}
              />
            )}
          </main>
        </div>
      </div>
    </div>
  );
}
