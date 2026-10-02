import { expect, it } from "vitest";
import { mentionAtCaret, mentionToken } from "./askComposer";

it("finds the active mention at the caret, keeping trailing text outside the replacement", () => {
  expect(mentionAtCaret("Compare @at with Cloud", 11)).toEqual({start: 8, end: 11, query: "at"});
  expect(mentionAtCaret("Compare @atlas with Cloud", 11)).toEqual({start: 8, end: 14, query: "at"});
  expect(mentionAtCaret("@note:deploy", 12)?.query).toBe("note:deploy");
  expect(mentionAtCaret("Email name@example.com", 22)).toBeNull();
  expect(mentionAtCaret('@note:"Deployment Plan"', 23)).toBeNull();
});

it("quotes names with spaces so picked mentions survive backend parsing", () => {
  expect(mentionToken({id: "1", ref: "note:Deployment Plan", name: "Plan", category: "note"})).toBe('@note:"Deployment Plan"');
  expect(mentionToken({id: "2", ref: "product:atlas-core", name: "Atlas", category: "product"})).toBe("@product:atlas-core");
});
