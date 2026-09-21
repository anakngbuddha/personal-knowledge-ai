import { useState } from "react";
import { api } from "../services/api";
import { setAccessToken } from "../services/http";

export function AuthScreen({ onAuthenticated }: { onAuthenticated: () => void }) {
  const [mode, setMode] = useState<"login" | "signup">("login");
  const [email, setEmail] = useState(""); const [password, setPassword] = useState("");
  const [name, setName] = useState(""); const [org, setOrg] = useState("");
  const [error, setError] = useState<string | null>(null); const [busy, setBusy] = useState(false);
  async function submit(e: React.FormEvent) { e.preventDefault(); setBusy(true); setError(null); try {
    const result = mode === "login" ? await api.login(email, password) : await api.signup({ email, password, display_name: name, organization_name: org });
    setAccessToken(result.access_token); onAuthenticated();
  } catch (err) { setError(err instanceof Error ? err.message : "Could not sign in"); } finally { setBusy(false); } }
  return <div className="auth-screen"><form className="auth-card" onSubmit={submit}><p className="kicker">SE Field Desk</p><h1>{mode === "login" ? "Welcome back" : "Create your workspace"}</h1>
    {mode === "signup" && <><input required placeholder="Your name" value={name} onChange={e => setName(e.target.value)} /><input required placeholder="Organization name" value={org} onChange={e => setOrg(e.target.value)} /></>}
    <input required type="email" placeholder="Work email" value={email} onChange={e => setEmail(e.target.value)} /><input required minLength={10} type="password" placeholder="Password (10+ characters)" value={password} onChange={e => setPassword(e.target.value)} />
    {error && <div className="banner error">{error}</div>}<button className="primary" disabled={busy}>{busy ? "Working…" : mode === "login" ? "Sign in" : "Create account"}</button>
    <button type="button" className="link-button" onClick={() => setMode(mode === "login" ? "signup" : "login")}>{mode === "login" ? "New here? Create an account" : "Already have an account? Sign in"}</button>
  </form></div>;
}
