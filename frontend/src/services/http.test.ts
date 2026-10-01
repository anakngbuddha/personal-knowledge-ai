import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

class MemoryStorage implements Storage {
  private values = new Map<string, string>();
  get length() { return this.values.size; }
  clear() { this.values.clear(); }
  getItem(key: string) { return this.values.get(key) ?? null; }
  key(index: number) { return [...this.values.keys()][index] ?? null; }
  removeItem(key: string) { this.values.delete(key); }
  setItem(key: string, value: string) { this.values.set(key, value); }
}

let local: MemoryStorage;
let session: MemoryStorage;

beforeEach(() => {
  local = new MemoryStorage();
  session = new MemoryStorage();
  vi.stubGlobal("localStorage", local);
  vi.stubGlobal("sessionStorage", session);
  vi.resetModules();
});

afterEach(() => {
  vi.unstubAllGlobals();
  vi.unstubAllEnvs();
});

describe("API origin security", () => {
  it("ignores hostile query and persisted API overrides", async () => {
    vi.stubGlobal("window", { location: { hostname: "workspace.example", search: "?api=https://attacker.example" } });
    vi.stubEnv("VITE_API_BASE_URL", "https://api.example");
    local.setItem("pka_api_base_url", "https://attacker.example");
    const http = await import("./http");
    http.setAccessToken("private-token");
    const fetchMock = vi.fn().mockResolvedValue(new Response("{}"));
    vi.stubGlobal("fetch", fetchMock);
    await http.fetchResponse("/auth/me");
    expect(fetchMock.mock.calls[0][0]).toBe("https://api.example/auth/me");
    expect(fetchMock.mock.calls[0][1].redirect).toBe("error");
  });

  it("rejects absolute and protocol-relative paths before attaching tokens", async () => {
    const http = await import("./http");
    http.setAccessToken("private-token");
    const fetchMock = vi.fn();
    vi.stubGlobal("fetch", fetchMock);
    for (const path of ["https://attacker.example", "//attacker.example", "/\\attacker.example"]) {
      await expect(http.fetchResponse(path)).rejects.toThrow("Invalid API path");
    }
    expect(fetchMock).not.toHaveBeenCalled();
  });
});

describe("authentication session", () => {
  it("never persists bearer tokens when remembering is requested", async () => {
    const http = await import("./http");
    http.setAccessToken("remembered-token", { remember: true, expiresInSeconds: 3600 });
    expect(local.getItem("pka_remembered_session")).toBeNull();

    vi.stubGlobal("sessionStorage", new MemoryStorage());
    vi.resetModules();
    const reopened = await import("./http");
    expect(reopened.getAccessToken()).toBeNull();
  });

  it("does not restore a login when remembering is disabled", async () => {
    const http = await import("./http");
    http.setAccessToken("tab-only", { remember: false, expiresInSeconds: 3600 });
    expect(session.getItem("pka_access_token")).toBe("tab-only");

    vi.stubGlobal("sessionStorage", new MemoryStorage());
    vi.resetModules();
    expect((await import("./http")).getAccessToken()).toBeNull();
  });

  it("removes an expired remembered login", async () => {
    const http = await import("./http");
    http.setAccessToken("expired-token", { remember: true, expiresInSeconds: 3600 });
    local.setItem("pka_remembered_session", JSON.stringify({ token: "expired-token", expiresAt: Date.now() - 1 }));

    session.clear();
    expect(http.getAccessToken()).toBeNull();
    expect(local.getItem("pka_remembered_session")).toBeNull();
  });

  it("shows a credential error on login 401 and never sends the old bearer token", async () => {
    const http = await import("./http");
    http.setAccessToken("old-token", { remember: true, expiresInSeconds: 3600 });
    const fetchMock = vi.fn().mockResolvedValue(new Response(JSON.stringify({ detail: "Email or password is incorrect" }), { status: 401 }));
    vi.stubGlobal("fetch", fetchMock);

    await expect(http.fetchResponse("/auth/login", { method: "POST" })).rejects.toThrow("Email or password is incorrect.");
    expect(new Headers(fetchMock.mock.calls[0][1].headers).get("Authorization")).toBeNull();
    expect(http.getAccessToken()).toBe("old-token");
  });

  it("clears a rejected protected session and notifies the app", async () => {
    const http = await import("./http");
    http.setAccessToken("revoked-token", { remember: true, expiresInSeconds: 3600 });
    const expired = vi.fn();
    http.onSessionExpired(expired);
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response(null, { status: 401 })));

    await expect(http.fetchResponse("/auth/me")).rejects.toThrow("session expired");
    expect(http.getAccessToken()).toBeNull();
    expect(expired).toHaveBeenCalledOnce();
  });

  it("does not erase a newer login when an older request returns 401", async () => {
    const http = await import("./http");
    http.setAccessToken("old-token");
    let finish!: (response: Response) => void;
    vi.stubGlobal("fetch", vi.fn().mockImplementation(() => new Promise<Response>((resolve) => { finish = resolve; })));

    const oldRequest = http.fetchResponse("/auth/me");
    http.setAccessToken("new-token");
    finish(new Response(null, { status: 401 }));
    await expect(oldRequest).rejects.toThrow("session expired");
    expect(http.getAccessToken()).toBe("new-token");
  });
});
