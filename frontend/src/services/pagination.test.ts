import { expect, it } from "vitest";
import { pageCursor } from "./pagination";

it("encodes stable timestamp and UUID cursor fields as URL-safe data", () => {
  const id = "4c875d2b-63dc-496f-966a-9e3531e6d1ca";
  const cursor = pageCursor("2026-10-01T00:00:00Z", id);
  expect(cursor).toMatch(/^[A-Za-z0-9_-]+$/);
  const decoded = JSON.parse(atob(cursor.replace(/-/g, "+").replace(/_/g, "/")));
  expect(decoded).toEqual({timestamp: "2026-10-01T00:00:00.000Z", id});
});
