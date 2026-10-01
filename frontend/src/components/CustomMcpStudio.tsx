import React, { useEffect, useState } from "react";
import { api } from "../services/api";
import type { CustomMcpTool, McpServerConfig, McpServerStatus } from "../types";
import {
  ActivityIcon,
  CheckIcon,
  DatabaseIcon,
  ExternalLinkIcon,
  InfoIcon,
  NetworkIcon,
  RefreshCwIcon,
  SearchIcon,
  ZapIcon,
} from "./Icons";

export function CustomMcpStudio() {
  const [status, setStatus] = useState<McpServerStatus | null>(null);
  const [config, setConfig] = useState<McpServerConfig | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [copiedKey, setCopiedKey] = useState<string | null>(null);

  // Active view tab
  const [activeTab, setActiveTab] = useState<"claude" | "cursor" | "console" | "manifest">("claude");
  const [claudeMode, setClaudeMode] = useState<"python_remote" | "npx_remote" | "local_script">("python_remote");

  // Console testing state
  const [selectedToolName, setSelectedToolName] = useState<string>("search_knowledge");
  const [toolArgumentsJson, setToolArgumentsJson] = useState<string>(
    JSON.stringify({ query: "Huawei Cloud SLA comparison", top_k: 3 }, null, 2)
  );
  const [executing, setExecuting] = useState(false);
  const [executionResult, setExecutionResult] = useState<string | null>(null);
  const [executionIsError, setExecutionIsError] = useState(false);

  // Token management
  const [generatedToken, setGeneratedToken] = useState<string | null>(null);
  const [generatingToken, setGeneratingToken] = useState(false);

  async function loadData() {
    setLoading(true);
    setError(null);
    try {
      const [statusRes, configRes] = await Promise.all([
        api.getCustomMcpStatus(),
        api.getCustomMcpConfig(),
      ]);
      setStatus(statusRes);
      setConfig(configRes);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load MCP server state");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    void loadData();
  }, []);

  function handleToolSelect(tool: CustomMcpTool) {
    setSelectedToolName(tool.name);
    // Auto-populate default sample parameters
    let sample: Record<string, unknown> = {};
    if (tool.name === "search_knowledge") {
      sample = { query: "PostgreSQL pgvector performance benchmarks", top_k: 5 };
    } else if (tool.name === "read_document") {
      sample = { document_id: "00000000-0000-0000-0000-000000000000" };
    } else if (tool.name === "list_documents") {
      sample = { limit: 10, offset: 0 };
    } else if (tool.name === "ask_intelligence") {
      sample = {
        question: "What are the high availability requirements for enterprise deployments?",
        enable_web_search: true,
        strict_mode: false,
      };
    } else if (tool.name === "read_note") {
      sample = { note_id: "00000000-0000-0000-0000-000000000000" };
    } else if (tool.name === "list_notes") {
      sample = { limit: 10, offset: 0 };
    } else if (tool.name === "get_catalog_impact") {
      sample = { product: "PostgreSQL 16" };
    } else if (tool.name === "web_search") {
      sample = { query: "FastAPI performance benchmarks 2026", max_results: 5 };
    } else if (tool.name === "create_note") {
      sample = {
        title: "Claude Desktop Research Note",
        body: "# Sizing Analysis\n\nIdentified 3 potential prerequisites for [[PostgreSQL 16]].",
      };
    } else if (tool.name === "upload_text_document") {
      sample = {
        filename: "customer-sla-spec.md",
        content: "# Customer SLA Specification\n\n99.999% uptime required for core banking ledger.",
        title: "Customer SLA Spec",
        vendor: "Internal SE",
      };
    } else if (tool.name === "add_catalog_product") {
      sample = {
        name: "Redis Cache v7",
        vendor: "Redis Ltd",
        category: "In-Memory Cache",
        description: "High throughput distributed caching layer",
      };
    } else if (tool.name === "link_catalog_products") {
      sample = {
        source_product: "Redis Cache v7",
        target_product: "PostgreSQL 16",
        relation: "integrates_with",
        reason: "Used as write-through cache for frequent queries",
      };
    } else if (tool.name === "delete_note") {
      sample = { note_id: "00000000-0000-0000-0000-000000000000" };
    }
    setToolArgumentsJson(JSON.stringify(sample, null, 2));
    setExecutionResult(null);
  }

  async function handleExecuteTool() {
    setExecuting(true);
    setExecutionResult(null);
    setExecutionIsError(false);
    try {
      let parsedArgs: Record<string, unknown> = {};
      try {
        parsedArgs = JSON.parse(toolArgumentsJson);
      } catch (jsonErr) {
        throw new Error("Invalid JSON arguments syntax");
      }
      const res = await api.executeMcpTool(selectedToolName, parsedArgs);
      setExecutionResult(JSON.stringify(res.result, null, 2));
      setExecutionIsError(res.is_error);
    } catch (err) {
      setExecutionResult(JSON.stringify({ error: err instanceof Error ? err.message : String(err) }, null, 2));
      setExecutionIsError(true);
    } finally {
      setExecuting(false);
    }
  }

  async function handleGenerateToken() {
    setGeneratingToken(true);
    try {
      const res = await api.generateMcpToken("solutions_engineer", 60 * 24 * 30);
      setGeneratedToken(res.token);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to generate token");
    } finally {
      setGeneratingToken(false);
    }
  }

  function copyToClipboard(text: string, key: string) {
    void navigator.clipboard.writeText(text);
    setCopiedKey(key);
    setTimeout(() => setCopiedKey(null), 2500);
  }

  const selectedTool = status?.tools.find((t) => t.name === selectedToolName);

  return (
    <div className="custom-mcp-studio" style={{ padding: "8px 0" }}>
      {/* ── Top Hero Card ────────────────────────────────────────────── */}
      <div
        style={{
          background: "linear-gradient(135deg, rgba(30, 41, 59, 0.95), rgba(15, 23, 42, 0.98))",
          borderRadius: "16px",
          padding: "24px",
          color: "#fff",
          border: "1px solid rgba(255, 255, 255, 0.1)",
          boxShadow: "0 10px 30px rgba(0, 0, 0, 0.25)",
          marginBottom: "24px",
          position: "relative",
          overflow: "hidden",
        }}
      >
        <div
          style={{
            position: "absolute",
            top: "-40px",
            right: "-40px",
            width: "200px",
            height: "200px",
            background: "radial-gradient(circle, rgba(99, 102, 241, 0.25), transparent 70%)",
            borderRadius: "50%",
            pointerEvents: "none",
          }}
        />

        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", flexWrap: "wrap", gap: "16px" }}>
          <div>
            <div style={{ display: "flex", alignItems: "center", gap: "10px", marginBottom: "8px" }}>
              <div
                style={{
                  display: "inline-flex",
                  alignItems: "center",
                  gap: "6px",
                  padding: "4px 10px",
                  borderRadius: "20px",
                  background: "rgba(16, 185, 129, 0.15)",
                  border: "1px solid rgba(16, 185, 129, 0.4)",
                  color: "#10b981",
                  fontSize: "12px",
                  fontWeight: 600,
                  letterSpacing: "0.04em",
                }}
              >
                <span
                  style={{
                    width: "8px",
                    height: "8px",
                    borderRadius: "50%",
                    backgroundColor: "#10b981",
                    display: "inline-block",
                    boxShadow: "0 0 10px #10b981",
                  }}
                />
                CUSTOM MCP SERVER READY
              </div>
              <span style={{ fontSize: "12px", color: "rgba(255, 255, 255, 0.5)", fontFamily: "monospace" }}>
                Protocol v{status?.protocol_version || "2024-11-05"}
              </span>
            </div>

            <h2 style={{ fontSize: "24px", fontWeight: 700, margin: "0 0 8px 0", letterSpacing: "-0.02em" }}>
              Expose Personal Knowledge AI as an MCP Server
            </h2>
            <p style={{ margin: 0, color: "rgba(255, 255, 255, 0.7)", maxWidth: "680px", fontSize: "14px", lineHeight: 1.5 }}>
              Enable external AI assistants like <strong>Claude Desktop</strong>, Cursor, and Antigravity to
              execute real-time <strong>Read &amp; Write commands</strong> directly into your knowledge base, solution
              catalog graph, and grounded retrieval engine.
            </p>
          </div>

          <div style={{ display: "flex", gap: "12px", flexWrap: "wrap" }}>
            <div
              style={{
                background: "rgba(255, 255, 255, 0.06)",
                padding: "10px 16px",
                borderRadius: "12px",
                border: "1px solid rgba(255, 255, 255, 0.08)",
                textAlign: "center",
              }}
            >
              <div style={{ fontSize: "11px", color: "rgba(255, 255, 255, 0.5)", textTransform: "uppercase" }}>Read Tools</div>
              <div style={{ fontSize: "20px", fontWeight: 700, color: "#38bdf8" }}>{status?.read_tools_count ?? 8}</div>
            </div>
            <div
              style={{
                background: "rgba(255, 255, 255, 0.06)",
                padding: "10px 16px",
                borderRadius: "12px",
                border: "1px solid rgba(255, 255, 255, 0.08)",
                textAlign: "center",
              }}
            >
              <div style={{ fontSize: "11px", color: "rgba(255, 255, 255, 0.5)", textTransform: "uppercase" }}>Write Tools</div>
              <div style={{ fontSize: "20px", fontWeight: 700, color: "#34d399" }}>{status?.write_tools_count ?? 5}</div>
            </div>
            <div
              style={{
                background: "rgba(255, 255, 255, 0.06)",
                padding: "10px 16px",
                borderRadius: "12px",
                border: "1px solid rgba(255, 255, 255, 0.08)",
                textAlign: "center",
              }}
            >
              <div style={{ fontSize: "11px", color: "rgba(255, 255, 255, 0.5)", textTransform: "uppercase" }}>Total Commands</div>
              <div style={{ fontSize: "20px", fontWeight: 700, color: "#a78bfa" }}>{status?.tools_count ?? 13}</div>
            </div>
          </div>
        </div>

        {/* Quick Tabs */}
        <div style={{ display: "flex", gap: "8px", marginTop: "24px", borderTop: "1px solid rgba(255, 255, 255, 0.1)", paddingTop: "16px" }}>
          <button
            type="button"
            onClick={() => setActiveTab("claude")}
            aria-pressed={activeTab === "claude"}
            style={{
              padding: "8px 16px",
              borderRadius: "8px",
              border: "none",
              cursor: "pointer",
              fontWeight: 600,
              fontSize: "13px",
              background: activeTab === "claude" ? "rgba(255, 255, 255, 0.2)" : "transparent",
              color: activeTab === "claude" ? "#fff" : "rgba(255, 255, 255, 0.6)",
              transition: "all 0.15s ease",
            }}
          >
            Claude Desktop Setup
          </button>
          <button
            type="button"
            onClick={() => setActiveTab("cursor")}
            aria-pressed={activeTab === "cursor"}
            style={{
              padding: "8px 16px",
              borderRadius: "8px",
              border: "none",
              cursor: "pointer",
              fontWeight: 600,
              fontSize: "13px",
              background: activeTab === "cursor" ? "rgba(255, 255, 255, 0.2)" : "transparent",
              color: activeTab === "cursor" ? "#fff" : "rgba(255, 255, 255, 0.6)",
              transition: "all 0.15s ease",
            }}
          >
            Cursor / IDE Setup
          </button>
          <button
            type="button"
            onClick={() => setActiveTab("console")}
            aria-pressed={activeTab === "console"}
            style={{
              padding: "8px 16px",
              borderRadius: "8px",
              border: "none",
              cursor: "pointer",
              fontWeight: 600,
              fontSize: "13px",
              background: activeTab === "console" ? "rgba(255, 255, 255, 0.2)" : "transparent",
              color: activeTab === "console" ? "#fff" : "rgba(255, 255, 255, 0.6)",
              transition: "all 0.15s ease",
            }}
          >
            Interactive Command Console
          </button>
          <button
            type="button"
            onClick={() => setActiveTab("manifest")}
            aria-pressed={activeTab === "manifest"}
            style={{
              padding: "8px 16px",
              borderRadius: "8px",
              border: "none",
              cursor: "pointer",
              fontWeight: 600,
              fontSize: "13px",
              background: activeTab === "manifest" ? "rgba(255, 255, 255, 0.2)" : "transparent",
              color: activeTab === "manifest" ? "#fff" : "rgba(255, 255, 255, 0.6)",
              transition: "all 0.15s ease",
            }}
          >
            Tools Manifest ({status?.tools.length || 13})
          </button>
        </div>
      </div>

      {error && (
        <div style={{ padding: "12px 16px", background: "rgba(239, 68, 68, 0.1)", border: "1px solid rgba(239, 68, 68, 0.3)", borderRadius: "8px", color: "#ef4444", marginBottom: "16px", fontSize: "13px" }}>
          {error}
        </div>
      )}

      {/* ── Tab 1: Claude Desktop Setup ────────────────────────────────── */}
      {/* ── Tab 1: Claude Desktop Setup ────────────────────────────────── */}
      {activeTab === "claude" && config && (() => {
        const activeSnippet =
          claudeMode === "npx_remote"
            ? (config.remote_npx_config || config.claude_desktop_config)
            : claudeMode === "local_script"
            ? {
                mcpServers: {
                  [config.server_name || "personal-knowledge-ai"]: {
                    command: "python",
                    args: ["mcp_server.py"],
                    env: {
                      PERSONAL_KNOWLEDGE_API_URL: config.api_url,
                      PERSONAL_KNOWLEDGE_API_KEY: ((config.remote_python_config as any)?.mcpServers?.[config.server_name]?.env?.PERSONAL_KNOWLEDGE_API_KEY) || "YOUR_TOKEN",
                    },
                  },
                },
              }
            : (config.remote_python_config || config.claude_desktop_config);

        return (
          <div style={{ display: "grid", gridTemplateColumns: "1fr", gap: "20px" }}>
            <div className="mcp-claude-panel" style={{ background: "var(--card-bg, #ffffff)", borderRadius: "12px", border: "1px solid var(--border-color, #e2e8f0)", padding: "20px", boxShadow: "0 1px 3px rgba(0,0,0,0.05)" }}>
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", marginBottom: "16px", flexWrap: "wrap", gap: "12px" }}>
                <div>
                  <h3 style={{ margin: "0 0 4px 0", fontSize: "16px", fontWeight: 700 }}>Claude Desktop Configuration</h3>
                  <p style={{ margin: 0, fontSize: "13px", color: "var(--text-muted, #64748b)" }}>
                    Connect Claude Desktop to your online knowledge base. Select your preferred connection method:
                  </p>
                </div>
                <div style={{ display: "flex", gap: "8px" }}>
                  <a
                    href={`${config.api_url || ""}/api/mcp/custom-server/script`}
                    download="mcp_server.py"
                    style={{
                      display: "inline-flex",
                      alignItems: "center",
                      gap: "6px",
                      padding: "8px 14px",
                      borderRadius: "8px",
                      background: "rgba(99, 102, 241, 0.1)",
                      color: "#4f46e5",
                      border: "1px solid rgba(99, 102, 241, 0.2)",
                      cursor: "pointer",
                      fontWeight: 600,
                      fontSize: "13px",
                      textDecoration: "none",
                      transition: "all 0.2s ease",
                    }}
                  >
                    <span>Download mcp_server.py</span>
                  </a>
                  <button
                    type="button"
                    onClick={() => copyToClipboard(JSON.stringify(activeSnippet, null, 2), "claude_config")}
                    style={{
                      display: "inline-flex",
                      alignItems: "center",
                      gap: "6px",
                      padding: "8px 14px",
                      borderRadius: "8px",
                      background: copiedKey === "claude_config" ? "#10b981" : "var(--accent-color, #4f46e5)",
                      color: "#fff",
                      border: "none",
                      cursor: "pointer",
                      fontWeight: 600,
                      fontSize: "13px",
                      transition: "all 0.2s ease",
                    }}
                  >
                    {copiedKey === "claude_config" ? <CheckIcon size={14} /> : <ZapIcon size={14} />}
                    <span>{copiedKey === "claude_config" ? "Copied!" : "Copy Configuration"}</span>
                  </button>
                </div>
              </div>

              {/* Mode Selector */}
              <div style={{ display: "flex", gap: "8px", marginBottom: "14px", background: "rgba(0,0,0,0.03)", padding: "4px", borderRadius: "8px" }}>
                <button
                  type="button"
                  onClick={() => setClaudeMode("python_remote")}
                  aria-pressed={claudeMode === "python_remote"}
                  style={{
                    flex: 1,
                    padding: "6px 12px",
                    borderRadius: "6px",
                    border: "none",
                    cursor: "pointer",
                    fontSize: "12px",
                    fontWeight: 600,
                    background: claudeMode === "python_remote" ? "#fff" : "transparent",
                    color: claudeMode === "python_remote" ? "#4f46e5" : "#64748b",
                    boxShadow: claudeMode === "python_remote" ? "0 1px 3px rgba(0,0,0,0.1)" : "none",
                  }}
                >
                  ⚡ Python Remote (Zero Download - Recommended)
                </button>
                <button
                  type="button"
                  onClick={() => setClaudeMode("npx_remote")}
                  aria-pressed={claudeMode === "npx_remote"}
                  style={{
                    flex: 1,
                    padding: "6px 12px",
                    borderRadius: "6px",
                    border: "none",
                    cursor: "pointer",
                    fontSize: "12px",
                    fontWeight: 600,
                    background: claudeMode === "npx_remote" ? "#fff" : "transparent",
                    color: claudeMode === "npx_remote" ? "#4f46e5" : "#64748b",
                    boxShadow: claudeMode === "npx_remote" ? "0 1px 3px rgba(0,0,0,0.1)" : "none",
                  }}
                >
                  🌐 NPX / SSE (Zero Download)
                </button>
                <button
                  type="button"
                  onClick={() => setClaudeMode("local_script")}
                  aria-pressed={claudeMode === "local_script"}
                  style={{
                    flex: 1,
                    padding: "6px 12px",
                    borderRadius: "6px",
                    border: "none",
                    cursor: "pointer",
                    fontSize: "12px",
                    fontWeight: 600,
                    background: claudeMode === "local_script" ? "#fff" : "transparent",
                    color: claudeMode === "local_script" ? "#4f46e5" : "#64748b",
                    boxShadow: claudeMode === "local_script" ? "0 1px 3px rgba(0,0,0,0.1)" : "none",
                  }}
                >
                  📁 Local File (Downloaded Script)
                </button>
              </div>

              <pre
                style={{
                  background: "#0f172a",
                  color: "#e2e8f0",
                  padding: "16px",
                  borderRadius: "8px",
                  fontSize: "12px",
                  fontFamily: "var(--font-mono, monospace)",
                  overflowX: "auto",
                  border: "1px solid #1e293b",
                  margin: "0 0 16px 0",
                }}
              >
                {JSON.stringify(activeSnippet, null, 2)}
              </pre>

              <div style={{ background: "rgba(99, 102, 241, 0.05)", border: "1px solid rgba(99, 102, 241, 0.2)", borderRadius: "8px", padding: "14px", fontSize: "13px", color: "var(--text-color, #1e293b)" }}>
                <div style={{ fontWeight: 600, marginBottom: "6px", display: "flex", alignItems: "center", gap: "6px", color: "#4f46e5" }}>
                  <InfoIcon size={15} /> How to connect Claude Desktop:
                </div>
                <ol style={{ margin: "0 0 0 18px", padding: 0, lineHeight: 1.6 }}>
                  <li>
                    Open your Claude Desktop configuration file:
                    <div style={{ margin: "4px 0", fontFamily: "monospace", fontSize: "12px", background: "rgba(0,0,0,0.04)", padding: "4px 8px", borderRadius: "4px" }}>
                      Windows: %APPDATA%\Claude\claude_desktop_config.json<br />
                      macOS: ~/Library/Application Support/Claude/claude_desktop_config.json
                    </div>
                  </li>
                  <li>
                    {claudeMode === "python_remote" && (
                      <span><strong>No file download needed!</strong> Claude will run Python and load the bridge in memory straight from your deployed server.</span>
                    )}
                    {claudeMode === "npx_remote" && (
                      <span><strong>No file download needed!</strong> Uses <code>npx</code> to stream requests over SSE directly to your server.</span>
                    )}
                    {claudeMode === "local_script" && (
                      <span>Download <code>mcp_server.py</code> above, place it in your chosen folder, and update the <code>args</code> path to its location.</span>
                    )}
                  </li>
                  <li>Paste the configuration snippet into the <code>mcpServers</code> section of the JSON file.</li>
                  <li>Completely restart Claude Desktop (exit from system tray).</li>
                  <li>Claude will now display the tools hammer with read and write capabilities!</li>
                </ol>
              </div>
            </div>
          </div>
        );
      })()}

      {/* ── Tab 2: Cursor / IDE Setup ──────────────────────────────────── */}
      {activeTab === "cursor" && config && (
        <div style={{ background: "var(--card-bg, #ffffff)", borderRadius: "12px", border: "1px solid var(--border-color, #e2e8f0)", padding: "20px" }}>
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "12px" }}>
            <div>
              <h3 style={{ margin: "0 0 4px 0", fontSize: "16px", fontWeight: 700 }}>Cursor MCP Setup</h3>
              <p style={{ margin: 0, fontSize: "13px", color: "var(--text-muted, #64748b)" }}>
                Add to your workspace's <code>.cursor/mcp.json</code> or configure in Cursor Settings &gt; Features &gt; MCP.
              </p>
            </div>
            <button
              type="button"
              onClick={() => copyToClipboard(JSON.stringify(config.cursor_config, null, 2), "cursor_config")}
              style={{
                display: "inline-flex",
                alignItems: "center",
                gap: "6px",
                padding: "8px 14px",
                borderRadius: "8px",
                background: copiedKey === "cursor_config" ? "#10b981" : "var(--accent-color, #4f46e5)",
                color: "#fff",
                border: "none",
                cursor: "pointer",
                fontWeight: 600,
                fontSize: "13px",
              }}
            >
              {copiedKey === "cursor_config" ? <CheckIcon size={14} /> : <ZapIcon size={14} />}
              <span>{copiedKey === "cursor_config" ? "Copied!" : "Copy Cursor JSON"}</span>
            </button>
          </div>

          <pre
            style={{
              background: "#0f172a",
              color: "#e2e8f0",
              padding: "16px",
              borderRadius: "8px",
              fontSize: "12px",
              fontFamily: "monospace",
              overflowX: "auto",
              border: "1px solid #1e293b",
            }}
          >
            {JSON.stringify(config.cursor_config, null, 2)}
          </pre>
        </div>
      )}

      {/* ── Tab 3: Interactive Command Console ─────────────────────────── */}
      {activeTab === "console" && status && (
        <div style={{ display: "grid", gridTemplateColumns: "300px 1fr", gap: "20px" }}>
          {/* Tool selector sidebar */}
          <div style={{ background: "var(--card-bg, #ffffff)", borderRadius: "12px", border: "1px solid var(--border-color, #e2e8f0)", padding: "16px", maxHeight: "650px", overflowY: "auto" }}>
            <div style={{ fontSize: "12px", fontWeight: 700, color: "var(--text-muted, #64748b)", textTransform: "uppercase", marginBottom: "12px" }}>
              Select Tool to Test
            </div>
            <div style={{ display: "flex", flexDirection: "column", gap: "6px" }}>
              {status.tools.map((t) => {
                const isSelected = t.name === selectedToolName;
                const isWrite = t.category === "write";
                return (
                  <button
                    key={t.name}
                    type="button"
                    onClick={() => handleToolSelect(t)}
                    aria-pressed={isSelected}
                    style={{
                      display: "flex",
                      flexDirection: "column",
                      alignItems: "flex-start",
                      padding: "8px 12px",
                      borderRadius: "8px",
                      border: isSelected ? "1.5px solid #4f46e5" : "1px solid var(--border-color, #e2e8f0)",
                      background: isSelected ? "rgba(99, 102, 241, 0.08)" : "transparent",
                      cursor: "pointer",
                      textAlign: "left",
                      transition: "all 0.15s ease",
                    }}
                  >
                    <div style={{ display: "flex", justifyContent: "space-between", width: "100%", alignItems: "center" }}>
                      <span style={{ fontWeight: isSelected ? 700 : 600, fontSize: "13px", color: isSelected ? "#4f46e5" : "var(--text-color, #1e293b)" }}>
                        {t.name}
                      </span>
                      <span
                        style={{
                          fontSize: "10px",
                          fontWeight: 700,
                          padding: "2px 6px",
                          borderRadius: "4px",
                          background: isWrite ? "rgba(16, 185, 129, 0.15)" : "rgba(56, 189, 248, 0.15)",
                          color: isWrite ? "#059669" : "#0284c7",
                          textTransform: "uppercase",
                        }}
                      >
                        {t.category}
                      </span>
                    </div>
                  </button>
                );
              })}
            </div>
          </div>

          {/* Test workspace */}
          <div style={{ display: "flex", flexDirection: "column", gap: "16px" }}>
            <div style={{ background: "var(--card-bg, #ffffff)", borderRadius: "12px", border: "1px solid var(--border-color, #e2e8f0)", padding: "20px" }}>
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "8px" }}>
                <div>
                  <h3 style={{ margin: "0 0 4px 0", fontSize: "16px", fontWeight: 700, display: "flex", alignItems: "center", gap: "8px" }}>
                    <span>{selectedToolName}</span>
                    <span
                      style={{
                        fontSize: "11px",
                        fontWeight: 700,
                        padding: "2px 8px",
                        borderRadius: "4px",
                        background: selectedTool?.category === "write" ? "rgba(16, 185, 129, 0.15)" : "rgba(56, 189, 248, 0.15)",
                        color: selectedTool?.category === "write" ? "#059669" : "#0284c7",
                        textTransform: "uppercase",
                      }}
                    >
                      {selectedTool?.category} command
                    </span>
                  </h3>
                  <p style={{ margin: 0, fontSize: "13px", color: "var(--text-muted, #64748b)" }}>
                    {selectedTool?.description}
                  </p>
                </div>

                <button
                  type="button"
                  onClick={() => void handleExecuteTool()}
                  disabled={executing}
                  style={{
                    display: "inline-flex",
                    alignItems: "center",
                    gap: "6px",
                    padding: "10px 18px",
                    borderRadius: "8px",
                    background: executing ? "#94a3b8" : "#4f46e5",
                    color: "#fff",
                    border: "none",
                    cursor: executing ? "not-allowed" : "pointer",
                    fontWeight: 600,
                    fontSize: "13px",
                  }}
                >
                  <RefreshCwIcon size={14} className={executing ? "spin" : ""} />
                  <span>{executing ? "Executing..." : "Run Command"}</span>
                </button>
              </div>

              <div style={{ marginTop: "16px" }}>
                <label style={{ display: "block", fontSize: "12px", fontWeight: 600, color: "var(--text-muted, #64748b)", marginBottom: "6px" }}>
                  JSON Arguments:
                </label>
                <textarea
                  value={toolArgumentsJson}
                  onChange={(e) => setToolArgumentsJson(e.target.value)}
                  rows={6}
                  style={{
                    width: "100%",
                    boxSizing: "border-box",
                    fontFamily: "var(--font-mono, monospace)",
                    fontSize: "12px",
                    padding: "12px",
                    borderRadius: "8px",
                    border: "1px solid var(--border-color, #cbd5e1)",
                    background: "var(--input-bg, #f8fafc)",
                    color: "var(--text-color, #0f172a)",
                  }}
                />
              </div>
            </div>

            {/* Response Output Inspector */}
            {executionResult && (
              <div
                style={{
                  background: "var(--card-bg, #ffffff)",
                  borderRadius: "12px",
                  border: `1px solid ${executionIsError ? "#f87171" : "var(--border-color, #e2e8f0)"}`,
                  padding: "20px",
                }}
              >
                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "8px" }}>
                  <span style={{ fontSize: "13px", fontWeight: 700, color: executionIsError ? "#dc2626" : "#059669" }}>
                    {executionIsError ? "Execution Error Response" : "Tool Execution Result (JSON-RPC)"}
                  </span>
                  <button
                    type="button"
                    onClick={() => copyToClipboard(executionResult, "res")}
                    style={{
                      background: "transparent",
                      border: "none",
                      color: "var(--accent-color, #4f46e5)",
                      fontSize: "12px",
                      cursor: "pointer",
                      fontWeight: 600,
                    }}
                  >
                    {copiedKey === "res" ? "Copied" : "Copy Output"}
                  </button>
                </div>
                <pre
                  style={{
                    background: "#0f172a",
                    color: executionIsError ? "#fca5a5" : "#86efac",
                    padding: "14px",
                    borderRadius: "8px",
                    fontSize: "12px",
                    fontFamily: "monospace",
                    maxHeight: "350px",
                    overflowY: "auto",
                    margin: 0,
                  }}
                >
                  {executionResult}
                </pre>
              </div>
            )}
          </div>
        </div>
      )}

      {/* ── Tab 4: Tools Manifest ──────────────────────────────────────── */}
      {activeTab === "manifest" && status && (
        <div style={{ background: "var(--card-bg, #ffffff)", borderRadius: "12px", border: "1px solid var(--border-color, #e2e8f0)", padding: "20px" }}>
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "16px" }}>
            <h3 style={{ margin: 0, fontSize: "16px", fontWeight: 700 }}>Full MCP Tools Manifest</h3>
            <span style={{ fontSize: "12px", color: "var(--text-muted, #64748b)" }}>
              {status.tools.length} commands exposed to external LLMs
            </span>
          </div>

          <div style={{ display: "flex", flexDirection: "column", gap: "10px" }}>
            {status.tools.map((t) => {
              const isWrite = t.category === "write";
              return (
                <div
                  key={t.name}
                  style={{
                    padding: "14px",
                    borderRadius: "8px",
                    border: "1px solid var(--border-color, #e2e8f0)",
                    background: "var(--bg-subtle, #f8fafc)",
                  }}
                >
                  <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "6px" }}>
                    <div style={{ display: "flex", alignItems: "center", gap: "10px" }}>
                      <code style={{ fontSize: "14px", fontWeight: 700, color: "#1e293b" }}>{t.name}</code>
                      <span
                        style={{
                          fontSize: "10px",
                          fontWeight: 700,
                          padding: "2px 6px",
                          borderRadius: "4px",
                          background: isWrite ? "rgba(16, 185, 129, 0.15)" : "rgba(56, 189, 248, 0.15)",
                          color: isWrite ? "#059669" : "#0284c7",
                          textTransform: "uppercase",
                        }}
                      >
                        {t.category}
                      </span>
                    </div>
                    <button
                      type="button"
                      onClick={() => {
                        handleToolSelect(t);
                        setActiveTab("console");
                      }}
                      style={{
                        background: "transparent",
                        border: "1px solid var(--border-color, #cbd5e1)",
                        borderRadius: "6px",
                        padding: "4px 10px",
                        fontSize: "12px",
                        cursor: "pointer",
                        fontWeight: 600,
                        color: "var(--accent-color, #4f46e5)",
                      }}
                    >
                      Test in Console &rarr;
                    </button>
                  </div>
                  <p style={{ margin: "0 0 8px 0", fontSize: "13px", color: "var(--text-muted, #64748b)" }}>
                    {t.description}
                  </p>
                  <div style={{ fontSize: "11px", color: "var(--text-muted, #94a3b8)", fontFamily: "monospace" }}>
                    Properties: {Object.keys(t.inputSchema.properties || {}).join(", ") || "none"}
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      )}
    </div>
  );
}
