import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it, vi } from "vitest";
import { SourcesWorkspace } from "./SourcesWorkspace";
import type { KnowledgeDocument } from "../types";

const document: KnowledgeDocument = {
  id: "source-1",
  original_filename: "guide.md",
  title: "Product Guide",
  file_type: "text/markdown",
  file_size: 1024,
  status: "ready",
  page_count: 3,
  chunk_count: 2,
  uploaded_at: "2026-01-01T00:00:00Z",
  processed_at: "2026-01-02T00:00:00Z",
  error_message: null,
  metadata_complete: true,
  version: 1,
  is_current: true,
  summary: "A guide to the product.",
};

function renderSources(selectedId: string | null = null) {
  return renderToStaticMarkup(
    <SourcesWorkspace
      documents={[document]}
      loading={false}
      error={null}
      refresh={vi.fn()}
      setError={vi.fn()}
      selectedId={selectedId}
      onSelect={vi.fn()}
      onNavigate={vi.fn()}
    />
  );
}

describe("SourcesWorkspace", () => {
  it("shows the source library and alternate views without the removed filter and inspector panels", () => {
    const markup = renderSources();

    expect(markup).toContain("Knowledge Sources");
    expect(markup).toContain("Library");
    expect(markup).toContain("Passages");
    expect(markup).toContain("Watches");
    expect(markup).toContain("Showing <strong>1</strong> source");
    expect(markup).toContain("Product Guide");
    expect(markup).not.toContain("Filter Sources");
    expect(markup).not.toContain("Live Inspector");
  });

  it("keeps the source detail dialog closed until a source is selected", () => {
    expect(renderSources()).not.toContain('role="dialog"');
    const selectedMarkup = renderSources("source-1");
    expect(selectedMarkup).toContain('role="dialog"');
    expect(selectedMarkup).toContain('aria-labelledby="source-detail-title"');
    expect(selectedMarkup).toContain("Close source details");
  });

  it("keeps per-source inspect and Ask AI actions in the card", () => {
    const markup = renderSources();
    expect(markup).toContain("Inspect");
    expect(markup).toContain("Ask AI");
  });
});
