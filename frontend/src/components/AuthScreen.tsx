import { useState } from "react";
import { api } from "../services/api";
import { setAccessToken } from "../services/http";

export function AuthScreen({ onAuthenticated }: { onAuthenticated: () => void }) {
  const [mode, setMode] = useState<"login" | "signup">("login");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [name, setName] = useState("");
  const [org, setOrg] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

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
      setAccessToken(result.access_token);
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
        <p className="kicker">Knowledge Advisor</p>
        <h1>{mode === "login" ? "Sign in" : "Create workspace"}</h1>

        {mode === "signup" && (
          <>
            <div className="form-group">
              <label htmlFor="name">Full Name</label>
              <input
                id="name"
                required
                placeholder="Your name"
                value={name}
                onChange={(e) => setName(e.target.value)}
                disabled={busy}
              />
            </div>
            <div className="form-group">
              <label htmlFor="org">Organization</label>
              <input
                id="org"
                required
                placeholder="Company or team"
                value={org}
                onChange={(e) => setOrg(e.target.value)}
                disabled={busy}
              />
            </div>
          </>
        )}

        <div className="form-group">
          <label htmlFor="email">Email</label>
          <input
            id="email"
            required
            type="email"
            placeholder="you@example.com"
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
              {validatePassword(password) ? `✗ ${validatePassword(password)}` : "✓ Strong password"}
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
              placeholder="Repeat password"
              value={confirmPassword}
              onChange={(e) => setConfirmPassword(e.target.value)}
              disabled={busy}
            />
          </div>
        )}

        {error && <div className="banner error">{error}</div>}

        <button className="primary" disabled={busy}>
          {busy ? "Loading…" : mode === "login" ? "Sign in" : "Create account"}
        </button>

        <button
          type="button"
          className="link-button"
          onClick={() => {
            setMode(mode === "login" ? "signup" : "login");
            setError(null);
            setPassword("");
            setConfirmPassword("");
          }}
        >
          {mode === "login" ? "New here? Create an account" : "Already have an account? Sign in"}
        </button>
      </form>
    </div>
  );
}
