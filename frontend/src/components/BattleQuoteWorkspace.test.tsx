// @vitest-environment happy-dom
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { BattleQuoteWorkspace } from "./BattleQuoteWorkspace";
import type { PrincipalProfile } from "../types";

const { list, get, coverage, quoteRender, claimRender, setupRender } = vi.hoisted(() => ({
  list: vi.fn(), get: vi.fn(), coverage: vi.fn(), quoteRender: vi.fn(), claimRender: vi.fn(), setupRender: vi.fn(),
}));
vi.mock("../services/opportunities", () => ({ opportunityApi: { list, get, coverage } }));
vi.mock("./QuotePanel", () => ({ QuotePanel: (props: unknown) => { quoteRender(props); return <p>Quote workspace</p>; } }));
vi.mock("./ClaimsPanel", () => ({ ClaimsPanel: (props: unknown) => { claimRender(props); return <p>Claim workspace</p>; } }));
vi.mock("./TenantPricingSetup", () => ({ TenantPricingSetup: (props: unknown) => { setupRender(props); return <p>Administrator pricing setup</p>; } }));

const sales: PrincipalProfile = { org_id: "org-1", user_id: "user-1", role: "sales", can_write_catalog: false };
const admin: PrincipalProfile = { ...sales, role: "admin", is_admin: true, can_write_catalog: true };
const deal = { id: "deal-1", title: "Cloud migration", currency: "USD" };
const baseProps = { principal: sales, onSelectOpportunity: vi.fn(), onOpenOpportunity: vi.fn() };
beforeEach(() => {
  list.mockResolvedValue({ items: [deal], limit: 50 });
  get.mockResolvedValue(deal);
  coverage.mockResolvedValue({ ready_for_quote: true });
});
afterEach(() => { cleanup(); vi.resetAllMocks(); });

describe("Battle Quote", () => {
  it("loads a linked opportunity outside the first list page and preserves coverage handoff", async () => {
    list.mockResolvedValue({ items: [], limit: 50 });
    render(<BattleQuoteWorkspace {...baseProps} opportunityId="deal-1" />);
    await waitFor(() => expect(screen.getByText("Quote workspace")).toBeTruthy());
    expect(get).toHaveBeenCalledWith("deal-1");
    expect(quoteRender).toHaveBeenLastCalledWith(expect.objectContaining({ opportunityId: "deal-1", currency: "USD", coverageReady: true, canApprove: false }));
    fireEvent.click(screen.getByRole("button", { name: "Review requirements" }));
    expect(baseProps.onOpenOpportunity).toHaveBeenCalledWith("deal-1");
    fireEvent.click(screen.getByRole("button", { name: "Battle cards" }));
    expect(claimRender).toHaveBeenLastCalledWith(expect.objectContaining({ opportunityId: "deal-1", canReview: false }));
  });

  it("opens tenant setup for admins and forwards quote and claim approval privileges", async () => {
    render(<BattleQuoteWorkspace {...baseProps} principal={admin} opportunityId="deal-1" />);
    await waitFor(() => expect(quoteRender).toHaveBeenCalledWith(expect.objectContaining({ canApprove: true })));
    fireEvent.click(screen.getByRole("button", { name: "Battle cards" }));
    expect(claimRender).toHaveBeenCalledWith(expect.objectContaining({ canReview: true }));
    fireEvent.click(screen.getByRole("button", { name: "Tenant setup" }));
    expect(screen.getByText("Administrator pricing setup")).toBeTruthy();
  });

  it("explains required tenant setup without exposing admin forms to sales", () => {
    render(<BattleQuoteWorkspace {...baseProps} />);
    fireEvent.click(screen.getByRole("button", { name: "Tenant setup" }));
    expect(screen.getByText(/Your tenant administrator configures Azure/)).toBeTruthy();
    expect(setupRender).not.toHaveBeenCalled();
  });

  it("does not fetch sales data for an unauthorized viewer", () => {
    render(<BattleQuoteWorkspace {...baseProps} principal={{ ...sales, role: "viewer" }} />);
    expect(screen.getByText(/Ask your tenant administrator for access/)).toBeTruthy();
    expect(list).not.toHaveBeenCalled();
    expect(get).not.toHaveBeenCalled();
  });

  it("reports unavailable opportunity access without loading a quote for another deal", async () => {
    get.mockRejectedValue(new Error("Opportunity not found"));
    render(<BattleQuoteWorkspace {...baseProps} opportunityId="foreign-deal" />);
    await waitFor(() => expect(screen.getByRole("alert").textContent).toContain("Opportunity not found"));
    expect(quoteRender).not.toHaveBeenCalled();
  });
});
