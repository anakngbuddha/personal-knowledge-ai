// @vitest-environment happy-dom
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { ClaimsPanel } from "./ClaimsPanel";

const { list, sources, create, decide, battleCard } = vi.hoisted(() => ({
  list: vi.fn(), sources: vi.fn(), create: vi.fn(), decide: vi.fn(), battleCard: vi.fn(),
}));
vi.mock("../services/salesClaims", () => ({ salesClaimsApi: { list, sources, create, decide, battleCard } }));
afterEach(() => { cleanup(); vi.resetAllMocks(); });

function setup() {
  list.mockResolvedValue({ items: [] });
  sources.mockResolvedValue({ items: [{ id: "source-1", title: "Vendor guide", version: 1, approval_state: "approved" }] });
  create.mockResolvedValue({ id: "claim-1" });
  battleCard.mockResolvedValue({ items: [] });
}

describe("ClaimsPanel", () => {
  it("creates a draft with a chosen source, anchor, and explicit validity", async () => {
    setup(); render(<ClaimsPanel opportunityId="deal-1" />);
    await waitFor(() => expect(screen.getByText("Vendor guide · v1 · approved")).toBeTruthy());
    fireEvent.change(screen.getByLabelText("Statement"), { target: { value: "Supports security keys" } });
    fireEvent.change(screen.getByLabelText("Evidence source"), { target: { value: "source-1" } });
    fireEvent.change(screen.getByLabelText("Page or section"), { target: { value: "Section 3" } });
    fireEvent.change(screen.getByLabelText("Valid until"), { target: { value: "2026-12-31" } });
    fireEvent.click(screen.getByRole("button", { name: "Save draft claim" }));
    await waitFor(() => expect(create).toHaveBeenCalledWith("deal-1", expect.objectContaining({
      statement: "Supports security keys", source_document_id: "source-1", source_anchor: "Section 3", valid_until: "2026-12-31",
    })));
    expect(decide).not.toHaveBeenCalled();
  });

  it("requires a review rationale and reports approval denial", async () => {
    setup(); list.mockResolvedValue({ items: [{ id: "claim-1", statement: "A draft", status: "draft", version: 1, source_anchor: "Section 3", source_version: 1, valid_until: "2026-12-31" }] });
    decide.mockRejectedValue(new Error("A separate reviewer is required"));
    render(<ClaimsPanel opportunityId="deal-1" canReview />);
    await waitFor(() => expect(screen.getByText("A draft")).toBeTruthy());
    expect((screen.getByRole("button", { name: "Approve claim (reviewer)" }) as HTMLButtonElement).disabled).toBe(true);
    fireEvent.change(screen.getByLabelText("Review rationale"), { target: { value: "Checked source" } });
    fireEvent.click(screen.getByRole("button", { name: "Approve claim (reviewer)" }));
    await waitFor(() => expect(screen.getByRole("alert").textContent).toContain("A separate reviewer"));
    expect(decide).toHaveBeenCalledWith("claim-1", "approve", 1, "Checked source");
  });

  it("uses only server-approved current evidence for a battle card preview", async () => {
    setup(); render(<ClaimsPanel opportunityId="deal-1" />);
    fireEvent.click(screen.getByRole("button", { name: "Preview customer-safe battle card" }));
    await waitFor(() => expect(screen.getByText("No current public claims approved for this page.")).toBeTruthy());
    expect(battleCard).toHaveBeenCalledWith("deal-1", 0);
  });
});
