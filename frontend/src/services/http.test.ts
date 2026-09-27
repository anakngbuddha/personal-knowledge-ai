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
});

describe("authentication session", () => {
  it("restores a remembered login after browser session storage is cleared", async () => {
    const http = await import("./http");
    http.setAccessToken("remembered-token", { remember: true, expiresInSeconds: 3600 });
    expect(session.length).toBe(0);

    vi.stubGlobal("sessionStorage", new MemoryStorage());
    vi.resetModules();
    const reopened = await import("./http");
    expect(reopened.getAccessToken()).toBe("remembered-token");
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
