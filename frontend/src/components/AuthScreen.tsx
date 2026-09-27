import React, { useState } from "react";
import { LogoMark, ShieldCheckIcon } from "./Icons";
import { api } from "../services/api";
import { setAccessToken } from "../services/http";

export function AuthScreen({
  onAuthenticated,
  onBack,
}: {
  onAuthenticated: () => void;
  onBack?: () => void;
}) {
  const [mode, setMode] = useState<"login" | "signup">("login");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [name, setName] = useState("");
  const [org, setOrg] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [remember, setRemember] = useState(true);

  const validatePassword = (pwd: string) => {
    if (pwd.length < 10) return "Password must be at least 10 characters";
    if (!/[A-Z]/.test(pwd)) return "Must include an uppercase letter";
    if (!/[0-9]/.test(pwd)) return "Must include a number";
    return null;
  };

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);

    if (mode === "signup") {
      if (!name.trim()) {
        setError("Name is required");
        return;
      }
      if (!org.trim()) {
        setError("Organization is required");
        return;
      }
      const pwdErr = validatePassword(password);
      if (pwdErr) {
        setError(pwdErr);
        return;
      }
      if (password !== confirmPassword) {
        setError("Passwords do not match");
        return;
      }
    } else {
      if (!email.trim() || !password.trim()) {
        setError("Email and password required");
        return;
      }
    }

    setBusy(true);
    try {
      const result =
        mode === "login"
          ? await api.login(email, password)
          : await api.signup({ email, password, display_name: name, organization_name: org });
      setAccessToken(result.access_token, { remember, expiresInSeconds: result.expires_in_seconds });
      onAuthenticated();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Authentication failed");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="auth-screen">
      <form className="auth-card" onSubmit={submit}>
        {onBack && (
          <button
            type="button"
            onClick={onBack}
            className="auth-back-btn"
            style={{
              alignSelf: "flex-start",
              display: "inline-flex",
              alignItems: "center",
              gap: 6,
              background: "transparent",
              border: "none",
              color: "var(--text-muted)",
              fontSize: "12.5px",
              fontWeight: 500,
              cursor: "pointer",
              padding: "4px 8px",
              borderRadius: 6,
              marginBottom: 4,
              transition: "color 150ms ease, background 150ms ease",
            }}
          >
            ← Back to Overview
          </button>
        )}
        <div className="auth-header">
          <div className="brand-emblem" style={{ width: 48, height: 48, margin: "0 auto 8px" }}>
            <LogoMark size={48} />
          </div>
          <p className="kicker">Deep Atlas AI</p>
          <h1>{mode === "login" ? "Welcome back" : "Create your workspace"}</h1>
          <p className="muted" style={{ margin: 0, fontSize: "13.5px" }}>
            {mode === "login"
              ? "Access your grounded enterprise knowledge base"
              : "Set up your secure, tenant-isolated AI environment"}
          </p>
        </div>

        {/* Segmented Mode Selector */}
        <div
          style={{
            display: "grid",
            gridTemplateColumns: "1fr 1fr",
            background: "rgba(255, 255, 255, 0.05)",
            padding: 4,
            borderRadius: 10,
            border: "1px solid var(--rule)",
            gap: 4,
          }}
        >
          <button
            type="button"
            style={{
              padding: "7px 12px",
              fontSize: "12px",
              fontWeight: 600,
              borderRadius: 7,
              border: 0,
              background: mode === "login" ? "var(--bg-surface-elevated)" : "transparent",
              color: mode === "login" ? "var(--text-primary)" : "var(--text-muted)",
              boxShadow: mode === "login" ? "var(--shadow-sm)" : "none",
            }}
            onClick={() => {
              setMode("login");
              setError(null);
            }}
          >
            Sign in
          </button>
          <button
            type="button"
            style={{
              padding: "7px 12px",
              fontSize: "12px",
              fontWeight: 600,
              borderRadius: 7,
              border: 0,
              background: mode === "signup" ? "var(--bg-surface-elevated)" : "transparent",
              color: mode === "signup" ? "var(--text-primary)" : "var(--text-muted)",
              boxShadow: mode === "signup" ? "var(--shadow-sm)" : "none",
            }}
            onClick={() => {
              setMode("signup");
              setError(null);
            }}
          >
            New Workspace
          </button>
        </div>

        {mode === "signup" && (
          <>
            <div className="form-group">
              <label htmlFor="name">Full Name</label>
              <input
                id="name"
                required
                placeholder="e.g. Alex Morgan"
                value={name}
                onChange={(e) => setName(e.target.value)}
                disabled={busy}
              />
            </div>
            <div className="form-group">
              <label htmlFor="org">Organization Name</label>
              <input
                id="org"
                required
                placeholder="e.g. Acme Systems"
                value={org}
                onChange={(e) => setOrg(e.target.value)}
                disabled={busy}
              />
            </div>
          </>
        )}

        <div className="form-group">
          <label htmlFor="email">Work Email</label>
          <input
            id="email"
            required
            type="email"
            placeholder="name@company.com"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            disabled={busy}
          />
        </div>

        <div className="form-group">
          <label htmlFor="password">Password</label>
          <input
            id="password"
            required
            minLength={10}
            type="password"
            placeholder={mode === "signup" ? "10+ characters, 1 uppercase, 1 number" : "••••••••"}
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            disabled={busy}
          />
          {mode === "signup" && password && (
            <small className={`password-strength ${validatePassword(password) ? "error" : "valid"}`}>
              {validatePassword(password) ? `✗ ${validatePassword(password)}` : "✓ Secure password"}
            </small>
          )}
        </div>

        {mode === "signup" && (
          <div className="form-group">
            <label htmlFor="confirm">Confirm Password</label>
            <input
              id="confirm"
              required
              type="password"
              placeholder="Repeat your password"
              value={confirmPassword}
              onChange={(e) => setConfirmPassword(e.target.value)}
              disabled={busy}
            />
          </div>
        )}

        <label className="auth-remember">
          <input type="checkbox" checked={remember} onChange={(e) => setRemember(e.target.checked)} disabled={busy} />
          <span>Keep me signed in after closing the browser</span>
        </label>

        {error && <div className="banner error">{error}</div>}

        <button className="primary" disabled={busy} style={{ width: "100%", padding: "11px 16px", fontSize: "13.5px" }}>
          {busy ? "Authenticating…" : mode === "login" ? "Sign in to Deep Atlas" : "Create Workspace"}
        </button>

        <div
          style={{
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            gap: 6,
            marginTop: 4,
            fontSize: "11px",
            color: "var(--text-muted)",
          }}
        >
          <ShieldCheckIcon size={14} style={{ color: "var(--forest-text)" }} />
          <span>Tenant Isolated • AES-256 Vector Encryption</span>
        </div>
      </form>
    </div>
  );
}
