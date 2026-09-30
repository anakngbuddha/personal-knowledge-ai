// @vitest-environment happy-dom
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { OpportunitiesWorkspace } from "./OpportunitiesWorkspace";

const { list, create, coverage, addRequirement, importRequirements, reviewRequirement } = vi.hoisted(() => ({
  list: vi.fn(), create: vi.fn(), coverage: vi.fn(), addRequirement: vi.fn(),
  importRequirements: vi.fn(), reviewRequirement: vi.fn(),
}));

vi.mock("../services/opportunities", () => ({
  opportunityApi: { list, create, coverage, addRequirement, importRequirements, reviewRequirement },
}));
vi.mock("./QuotePanel", () => ({ QuotePanel: () => null }));
vi.mock("./ClaimsPanel", () => ({ ClaimsPanel: () => null }));

afterEach(() => { cleanup(); vi.clearAllMocks(); });

describe("OpportunitiesWorkspace", () => {
  it("creates an opportunity and shows its coverage state", async () => {
    const opportunity = {
      id: "deal-1", account_id: null, workspace_id: "ws-1", owner_id: "user-1",
      title: "Customer migration", stage: "discovery", currency: "USD", version: 1,
      created_at: "2026-09-30T00:00:00Z",
    };
    list.mockResolvedValue({ items: [], limit: 50, offset: 0 });
    create.mockResolvedValue(opportunity);
    coverage.mockResolvedValue({
      opportunity_id: "deal-1", requirements: [], total: 0, limit: 50, offset: 0,
      mandatory_total: 0, mandatory_covered: 0, ready_for_quote: false,
    });

    render(<OpportunitiesWorkspace />);
    fireEvent.change(screen.getByLabelText("New opportunity"), { target: { value: "Customer migration" } });
    fireEvent.click(screen.getByRole("button", { name: "Create opportunity" }));

    await waitFor(() => expect(create).toHaveBeenCalledWith("Customer migration", "USD"));
    await waitFor(() => expect(coverage).toHaveBeenCalledWith("deal-1", 0));
    expect(screen.getByText("Coverage needs review")).toBeTruthy();
    expect(screen.getByText("Add requirement")).toBeTruthy();
  });

  it("reports API errors instead of losing the form", async () => {
    list.mockResolvedValue({ items: [], limit: 50, offset: 0 });
    create.mockRejectedValue(new Error("Permission denied"));
    render(<OpportunitiesWorkspace />);
    fireEvent.change(screen.getByLabelText("New opportunity"), { target: { value: "Denied deal" } });
    fireEvent.click(screen.getByRole("button", { name: "Create opportunity" }));
    await waitFor(() => expect(screen.getByRole("alert").textContent).toContain("Permission denied"));
    expect((screen.getByLabelText("New opportunity") as HTMLInputElement).value).toBe("Denied deal");
  });
});
