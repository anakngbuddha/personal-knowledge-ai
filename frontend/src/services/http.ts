import { SERVER_ASLEEP, friendlyError } from "./errors";

export class ApiError extends Error {
  constructor(public readonly status: number, public readonly detail: string) {
    super(`[${status}] ${friendlyError(status, detail)}`);
    this.name = "ApiError";
  }
}

function isBrowserLocalHost() {
  if (typeof window === "undefined") return true;
  const h = window.location.hostname;
  return h === "localhost" || h === "127.0.0.1";
}

function normalizeBase(url: string) {
  return url.trim().replace(/\/$/, "");
}

function readStoredBase() {
  if (typeof window === "undefined") return "";
  const q = new URLSearchParams(window.location.search).get("api")?.trim();
  if (q) {
    const c = normalizeBase(q);
    try {
      localStorage.setItem("pka_api_base_url", c);
    } catch {
      /* ignore private mode */
    }
    return c;
  }
  try {
    return normalizeBase(localStorage.getItem("pka_api_base_url") ?? "");
  } catch {
    return "";
  }
}

function resolveApiBaseUrl() {
  const s = readStoredBase();
  if (s) return s;
  const e = normalizeBase(import.meta.env.VITE_API_BASE_URL ?? "");
  if (e) return e;
  return isBrowserLocalHost() ? "http://localhost:8000" : "";
}

const BASE_URL = resolveApiBaseUrl();
const TOKEN_KEY = "pka_access_token";
const REMEMBERED_SESSION_KEY = "pka_remembered_session";
const FETCH_TIMEOUT_MS = 15000;
const WAKE_DELAYS_MS = [2000, 4000, 8000, 15000];

type WakePhase = "waking" | "awake" | "asleep";
const wakeListeners = new Set<(phase: WakePhase) => void>();
const expiredListeners = new Set<() => void>();
let wakeInFlight: Promise<boolean> | null = null;

export function apiBaseUrl() {
  return BASE_URL;
}

export function apiPointsAtLocalhostFromRemote() {
  return !isBrowserLocalHost() && (BASE_URL === "" || /localhost|127\.0\.0\.1/.test(BASE_URL));
}

export function getAccessToken() {
  try {
    const sessionToken = sessionStorage.getItem(TOKEN_KEY);
    if (sessionToken) return sessionToken;
  } catch {
    /* persistent storage may still be available */
  }
  try {
    const raw = localStorage.getItem(REMEMBERED_SESSION_KEY);
    if (!raw) return null;
    const saved: unknown = JSON.parse(raw);
    if (
      typeof saved === "object" && saved !== null &&
      "token" in saved && typeof saved.token === "string" &&
      "expiresAt" in saved && typeof saved.expiresAt === "number" &&
      Number.isFinite(saved.expiresAt) && saved.expiresAt > Date.now()
    ) return saved.token;
    localStorage.removeItem(REMEMBERED_SESSION_KEY);
    queueMicrotask(() => expiredListeners.forEach((listener) => listener()));
  } catch {
    try { localStorage.removeItem(REMEMBERED_SESSION_KEY); } catch { /* storage unavailable */ }
    queueMicrotask(() => expiredListeners.forEach((listener) => listener()));
  }
  return null;
}

export function setAccessToken(
  token: string | null,
  options?: { remember?: boolean; expiresInSeconds?: number },
) {
  try { sessionStorage.removeItem(TOKEN_KEY); } catch { /* storage unavailable */ }
  try { localStorage.removeItem(REMEMBERED_SESSION_KEY); } catch { /* storage unavailable */ }
  if (!token) return;
  if (options?.remember && options.expiresInSeconds && Number.isFinite(options.expiresInSeconds) && options.expiresInSeconds > 0) {
    try {
      localStorage.setItem(REMEMBERED_SESSION_KEY, JSON.stringify({
        token,
        expiresAt: Date.now() + options.expiresInSeconds * 1000,
      }));
      return;
    } catch {
      /* fall back to a browser-tab session when persistent storage is disabled */
    }
  }
  try { sessionStorage.setItem(TOKEN_KEY, token); } catch { /* storage unavailable */ }
}

export function onSessionExpired(listener: () => void) {
  expiredListeners.add(listener);
  return () => { expiredListeners.delete(listener); };
}

function expireAccessToken() {
  setAccessToken(null);
  expiredListeners.forEach((listener) => listener());
}

export function onServerWake(listener: (phase: WakePhase) => void) {
  wakeListeners.add(listener);
  return () => wakeListeners.delete(listener);
}

function notifyWake(phase: WakePhase) {
  for (const listener of wakeListeners) listener(phase);
}

function withAuthHeaders(path: string, init?: RequestInit) {
  const h = new Headers(init?.headers);
  const t = path === "/auth/login" || path === "/auth/signup" ? null : getAccessToken();
  if (t && !h.has("Authorization")) h.set("Authorization", `Bearer ${t}`);
  return h;
}

function timedSignal(parent?: AbortSignal | null, ms = FETCH_TIMEOUT_MS) {
  const c = new AbortController();
  const timer = setTimeout(() => c.abort(), ms);
  if (parent) {
    if (parent.aborted) c.abort();
    else parent.addEventListener("abort", () => c.abort(), { once: true });
  }
  return { signal: c.signal, cancel: () => clearTimeout(timer) };
}

function isColdStart(status: number | null, error: unknown) {
  if (status === 502 || status === 503) return true;
  if (error instanceof DOMException && error.name === "AbortError") return true;
  if (error instanceof TypeError) return true;
  return false;
}

async function readDetail(response: Response) {
  let detail = response.statusText;
  try {
    const body = await response.json();
    if (typeof body?.detail === "string") detail = body.detail;
    else if (Array.isArray(body?.detail)) detail = "Check the fields and try again.";
  } catch {
    /* keep status text */
  }
  return detail;
}

async function waitForServer(): Promise<boolean> {
  if (wakeInFlight) return wakeInFlight;
  wakeInFlight = (async () => {
    notifyWake("waking");
    for (const delay of WAKE_DELAYS_MS) {
      await new Promise((resolve) => setTimeout(resolve, delay));
      const timer = timedSignal(null, 8000);
      try {
        const response = await fetch(`${BASE_URL}/health`, { signal: timer.signal });
        if (response.ok) {
          notifyWake("awake");
          return true;
        }
      } catch {
        /* still starting */
      } finally {
        timer.cancel();
      }
    }
    notifyWake("asleep");
    return false;
  })().finally(() => {
    wakeInFlight = null;
  });
  return wakeInFlight;
}

async function fetchOnce(path: string, init?: RequestInit, timeoutMs = FETCH_TIMEOUT_MS) {
  const timer = timedSignal(init?.signal, timeoutMs);
  try {
    return await fetch(`${BASE_URL}${path}`, {
      ...init,
      headers: init?.headers,
      signal: timer.signal,
    });
  } catch (err) {
    if (err instanceof DOMException && err.name === "AbortError") {
      throw new Error(`Request timed out (${Math.round(timeoutMs / 1000)}s) for ${path}`);
    }
    throw err;
  } finally {
    timer.cancel();
  }
}

function defaultTimeoutForPath(path: string): number {
  if (
    path.startsWith("/ask") ||
    path.startsWith("/conversations") ||
    path.startsWith("/studio") ||
    path.startsWith("/workflows") ||
    path.startsWith("/graph/auto-graph")
  ) {
    return 120000;
  }
  return FETCH_TIMEOUT_MS;
}

/** Authenticated fetch that waits out a cold start before failing. */
export async function fetchResponse(
  path: string,
  init?: RequestInit,
  timeoutMs?: number
): Promise<Response> {
  const effectiveTimeout = timeoutMs ?? defaultTimeoutForPath(path);
  if (apiPointsAtLocalhostFromRemote()) {
    throw new Error("API URL is not set. Add VITE_API_BASE_URL and redeploy.");
  }
  let response: Response;
  const requestInit = { ...init, headers: withAuthHeaders(path, init) };
  const sentAuthorization = requestInit.headers.get("Authorization");
  try {
    response = await fetchOnce(path, requestInit, effectiveTimeout);
  } catch (error) {
    if (error instanceof Error && error.message.includes("timed out")) {
      throw error;
    }
    if (!isColdStart(null, error)) {
      throw error instanceof Error ? error : new Error("Could not reach the server.");
    }
    const woke = await waitForServer();
    if (!woke) throw new Error(SERVER_ASLEEP);
    response = await fetchOnce(path, requestInit, effectiveTimeout);
  }
  if (response.status === 502 || response.status === 503) {
    const woke = await waitForServer();
    if (!woke) throw new Error(SERVER_ASLEEP);
    response = await fetchOnce(path, requestInit, effectiveTimeout);
  }
  if (response.status === 401) {
    if (path === "/auth/login") throw new Error("Email or password is incorrect.");
    if (sentAuthorization) {
      if (sentAuthorization === `Bearer ${getAccessToken()}`) expireAccessToken();
      throw new Error(friendlyError(401, ""));
    }
    throw new Error("Please sign in to continue.");
  }
  if (!response.ok) {
    const detail = await readDetail(response);
    throw new ApiError(response.status, detail);
  }
  return response;
}

export async function request<T>(path: string, init?: RequestInit, timeoutMs?: number): Promise<T> {
  const response = await fetchResponse(path, init, timeoutMs);
  if (response.status === 204) return undefined as T;
  return (await response.json()) as T;
}

export async function requestBlob(path: string, init?: RequestInit, timeoutMs?: number) {
  const response = await fetchResponse(path, init, timeoutMs);
  const disposition = response.headers.get("Content-Disposition") ?? "";
  const match = /filename\*?=(?:UTF-8''|")?([^";]+)/i.exec(disposition);
  return {
    blob: await response.blob(),
    filename: decodeURIComponent((match?.[1] ?? "download.bin").replace(/["']/g, "")),
  };
}
