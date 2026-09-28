import { describe, expect, it } from "vitest";
import type { KnowledgeDocument } from "../types";
import { sortKnowledgeDocuments } from "./sourceSorting";

function source(
  original_filename: string,
  uploaded_at: string | null,
  processed_at: string | null = null,
  title?: string
): KnowledgeDocument {
  return {
    id: original_filename,
    original_filename,
    title,
    file_type: "text/markdown",
    file_size: 20,
    status: "ready",
    page_count: null,
    chunk_count: 1,
    uploaded_at,
    processed_at,
    error_message: null,
    metadata_complete: true,
    version: 1,
    is_current: true,
  };
}

describe("sortKnowledgeDocuments", () => {
  it("sorts by the newest processed or uploaded timestamp without mutating the list", () => {
    const rows = [
      source("older.md", "2026-01-01T00:00:00Z"),
      source("newer.md", "2026-02-01T00:00:00Z"),
      source("processed.md", "2025-12-01T00:00:00Z", "2026-03-01T00:00:00Z"),
    ];

    expect(sortKnowledgeDocuments(rows, "modified").map((row) => row.original_filename)).toEqual([
      "processed.md",
      "newer.md",
      "older.md",
    ]);
    expect(rows[0].original_filename).toBe("older.md");
  });

  it("sorts by the displayed title, falling back to the filename", () => {
    const rows = [
      source("zulu.md", null, null, "Zulu"),
      source("bravo.md", null, null, "Bravo"),
      source("alpha.md", null),
    ];

    expect(sortKnowledgeDocuments(rows, "name").map((row) => row.original_filename)).toEqual([
      "alpha.md",
      "bravo.md",
      "zulu.md",
    ]);
  });
});
