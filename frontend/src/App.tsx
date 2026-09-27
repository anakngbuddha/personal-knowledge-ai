import React, { useEffect, useState } from "react";
import { AuthScreen } from "./components/AuthScreen";
import { GraphExplorer } from "./components/GraphExplorer";
import { GroundedChat } from "./components/GroundedChat";
import { LandingPage } from "./components/LandingPage";
import {
  BookOpenIcon,
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
  const principal = usePrincipal(authenticated);

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
    { id: "ask", name: "Ask Intelligence", icon: StarIcon },
    { id: "notes", name: "Notes", icon: BookOpenIcon },
    { id: "sources", name: "Sources", icon: FileTextIcon, badge: documents.length > 0 ? String(documents.length) : undefined },
    { id: "connections", name: "Connectors", icon: ZapIcon },
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
          <div className="brand-emblem" title="Deep Atlas AI">
            <LogoMark size={28} />
          </div>
          <div className="brand-info">
            <div className="brand-title-wrap">
              <span className="brand-name">Deep Atlas</span>
            </div>
          </div>
        </div>

        <div className="mast-current-page" aria-label="Current page">{tabs.find((tab) => tab.id === activeTab)?.name}</div>

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
            <div className="user-info"><span className="user-name">{principal?.organization_name || "Workspace"}</span></div>
          </div>

          <button type="button" className="signout-btn" onClick={signOut} title="Sign out of workspace">
            <LogOutIcon size={14} />
            <span>Sign out</span>
          </button>
        </div>
      </header>

      {/* ── Main Workspace Body ─────────────────────────────────────── */}
      <div className="desk desk-unified">
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

          </nav>

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
                onMapChanged={() => setMapVersion((v) => v + 1)}
              />
            )}
            {activeTab === "notes" && <NotesPanel />}
            {activeTab === "settings" && <SettingsPanel principal={principal} onSignOut={signOut} theme={theme} onThemeChange={setTheme} />}
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
              />
            )}
          </main>
        </div>
      </div>
    </div>
  );
}
