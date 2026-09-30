// @vitest-environment happy-dom
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { QuotePanel } from "./QuotePanel";

const { policies, observations, quotes, create, transition, customerExport, signals } = vi.hoisted(() => ({
  policies: vi.fn(), observations: vi.fn(), quotes: vi.fn(), create: vi.fn(),
  transition: vi.fn(), customerExport: vi.fn(), signals: vi.fn(),
}));

vi.mock("../services/salesQuotes", () => ({
  salesQuotesApi: { policies, observations, quotes, create, transition, customerExport, signals },
}));

afterEach(() => { cleanup(); vi.clearAllMocks(); });

function setup() {
  signals.mockResolvedValue({ items: [] });
  policies.mockResolvedValue({ items: [{ id: "policy-1", version: "v1", currency: "USD", max_discount_percent: "0", min_margin_percent: "0", tax_percent: "0" }] });
  observations.mockResolvedValue({ items: [{ id: "rate-1", sku_map_id: "map-1", source_kind: "controlled_import", observation: { provider: "azure", sku: "vm-4", region: "eastus", unit: "hour", currency: "USD", unit_price: "1.25", expires_at: "2026-10-01T00:00:00Z" } }] });
  quotes.mockResolvedValue({ items: [] });
  create.mockResolvedValue({ id: "version-1", quote_id: "quote-1", number: 1, status: "draft", snapshot_sha256: "digest", result: { currency: "USD", total: "23.63", subtotal: "22.50", tax_total: "1.13", issueable: true, blockers: [], lines: [{ sku: "vm-4", provider: "azure", total_amount: "23.63", assumption: "two servers" }] } });
}

describe("QuotePanel", () => {
  it("shows actionable follow-up from stored records without offering discounts", async () => {
    setup();
    signals.mockResolvedValue({ items: [{ kind: "awaiting_approval", message: "Quote version 1 awaits approval" }] });
    render(<QuotePanel opportunityId="opp-1" currency="USD" coverageReady={true} />);
    await waitFor(() => expect(screen.getByText("Quote version 1 awaits approval")).toBeTruthy());
    expect(screen.queryByLabelText("Discount %")).toBeNull();
  });
  it("builds a multi-component draft from saved policies and rates", async () => {
    setup();
    render(<QuotePanel opportunityId="deal-1" currency="USD" coverageReady />);
    await waitFor(() => expect(screen.getByText("v1 · USD · list price")).toBeTruthy());
    fireEvent.change(screen.getByLabelText("Commercial policy"), { target: { value: "policy-1" } });
    fireEvent.change(screen.getByLabelText("Approved price observation"), { target: { value: "rate-1" } });
    fireEvent.change(screen.getByLabelText("Usage assumption"), { target: { value: "two servers" } });
    fireEvent.click(screen.getByRole("button", { name: "Add component" }));
    fireEvent.change(screen.getAllByLabelText("Approved price observation")[1], { target: { value: "rate-1" } });
    fireEvent.change(screen.getAllByLabelText("Usage assumption")[1], { target: { value: "backup server" } });
    fireEvent.click(screen.getByRole("button", { name: "Create priced draft" }));
    await waitFor(() => expect(create).toHaveBeenCalledOnce());
    expect(create.mock.calls[0][2]).toHaveLength(2);
    expect(screen.getByText("23.63 USD · 1 line")).toBeTruthy();
  });

  it("keeps existing versions visible while coverage needs review", async () => {
    setup();
    quotes.mockResolvedValue({ items: [{ id: "version-1", quote_id: "quote-1", number: 1, status: "issued", snapshot_sha256: "digest", result: { currency: "USD", total: "23.63", subtotal: "22.50", tax_total: "1.13", issueable: true, blockers: [], lines: [] } }] });
    render(<QuotePanel opportunityId="deal-1" currency="USD" coverageReady={false} />);
    await waitFor(() => expect(screen.getByText("Version 1")).toBeTruthy());
    expect(screen.queryByRole("button", { name: "Create priced draft" })).toBeNull();
    expect(screen.getByRole("button", { name: "Download customer quote" })).toBeTruthy();
  });
});
