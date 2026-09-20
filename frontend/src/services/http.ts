const BASE_URL = import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000";

const TOKEN_KEY = "pka_access_token";
const FETCH_TIMEOUT_MS = 15_000;

export function apiBaseUrl(): string {
  return BASE_URL;
}

export function getAccessToken(): string | null {
  try {
    return sessionStorage.getItem(TOKEN_KEY);
  } catch {
    return null;
  }
}

export function setAccessToken(token: string | null): void {
  try {
    if (token) sessionStorage.setItem(TOKEN_KEY, token);
    else sessionStorage.removeItem(TOKEN_KEY);
  } catch {
    /* private mode / unavailable storage */
  }
}

function withAuthHeaders(init?: RequestInit): Headers {
  const headers = new Headers(init?.headers);
  const token = getAccessToken();
  if (token && !headers.has("Authorization")) {
    headers.set("Authorization", `Bearer ${token}`);
  }
  return headers;
}

function timedSignal(parent?: AbortSignal | null): { signal: AbortSignal; cancel: () => void } {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), FETCH_TIMEOUT_MS);
  if (parent) {
    if (parent.aborted) controller.abort();
    else parent.addEventListener("abort", () => controller.abort(), { once: true });
  }
  return {
    signal: controller.signal,
    cancel: () => clearTimeout(timer),
  };
}

async function errorMessage(response: Response): Promise<string> {
  let detail = response.statusText;
  try {
    const body = await response.json();
    if (typeof body?.detail === "string") detail = body.detail;
    else if (Array.isArray(body?.detail)) detail = JSON.stringify(body.detail);
  } catch {
    /* non-JSON error body */
  }
  return detail;
}

function unreachable(err: unknown): Error {
  if (err instanceof DOMException && err.name === "AbortError") {
    return new Error("could not reach the API");
  }
  if (err instanceof TypeError) {
    return new Error("could not reach the API");
  }
  return err instanceof Error ? err : new Error("could not reach the API");
}

export async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const timed = timedSignal(init?.signal);
  try {
    const response = await fetch(`${BASE_URL}${path}`, {
      ...init,
      headers: withAuthHeaders(init),
      signal: timed.signal,
    });
    if (!response.ok) {
      throw new Error(await errorMessage(response));
    }
    if (response.status === 204) return undefined as T;
    return (await response.json()) as T;
  } catch (err) {
    throw unreachable(err);
  } finally {
    timed.cancel();
  }
}

export async function requestBlob(
  path: string,
  init?: RequestInit
): Promise<{ blob: Blob; filename: string }> {
  const timed = timedSignal(init?.signal);
  try {
    const response = await fetch(`${BASE_URL}${path}`, {
      ...init,
      headers: withAuthHeaders(init),
      signal: timed.signal,
    });
    if (!response.ok) {
      throw new Error(await errorMessage(response));
    }
    const disposition = response.headers.get("Content-Disposition") ?? "";
    const matched = /filename\*?=(?:UTF-8''|")?([^";]+)/i.exec(disposition);
    const raw = matched?.[1]?.trim() ?? "download.bin";
    const filename = decodeURIComponent(raw.replace(/["']/g, ""));
    return { blob: await response.blob(), filename };
  } catch (err) {
    throw unreachable(err);
  } finally {
    timed.cancel();
  }
}
