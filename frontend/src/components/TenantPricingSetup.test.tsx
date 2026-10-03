// @vitest-environment happy-dom
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { TenantPricingSetup } from "./TenantPricingSetup";

const { access, configureAccess, products, mappings, createMapping, approveMapping, capture, createPolicy, policies } = vi.hoisted(() => ({
  access: vi.fn(), configureAccess: vi.fn(), products: vi.fn(), mappings: vi.fn(), createMapping: vi.fn(),
  approveMapping: vi.fn(), capture: vi.fn(), createPolicy: vi.fn(), policies: vi.fn(),
}));
vi.mock("../services/salesSetup", async (original) => ({
  ...(await original<typeof import("../services/salesSetup")>()),
  salesSetupApi: { access, configureAccess, products, mappings, createMapping, approveMapping, capture, createPolicy },
}));
vi.mock("../services/salesQuotes", () => ({ salesQuotesApi: { policies } }));
const changed = vi.fn();
const mapping = { id: "map-1", product_id: "product-1", provider: "azure", service: "Virtual Machines", sku: "Standard_VM", meter: "Exact meter", region: "southeastasia", billing_mode: "pay_per_use", status: "draft" };
beforeEach(() => {
  access.mockResolvedValue({ items: [
    { provider: "azure", enabled: true, has_secret: false, requires_credentials: false },
    { provider: "aws", enabled: true, has_secret: true, requires_credentials: true },
    { provider: "gcp", enabled: false, has_secret: false, requires_credentials: true },
    { provider: "huawei", enabled: true, has_secret: true, requires_credentials: true },
  ] });
  products.mockResolvedValue({ items: [{ id: "product-1", name: "Cloud Compute", vendor: "Azure" }] });
  mappings.mockImplementation((status: string) => Promise.resolve({ items: [{ ...mapping, status }] }));
  policies.mockResolvedValue({ items: [] });
  configureAccess.mockResolvedValue({}); createMapping.mockResolvedValue(mapping); approveMapping.mockResolvedValue({}); capture.mockResolvedValue({ id: "price-1" }); createPolicy.mockResolvedValue({ id: "policy-1" });
});
afterEach(() => { cleanup(); vi.resetAllMocks(); });

describe("Tenant pricing setup", () => {
  it("saves AWS tenant credentials, clears secret fields, and can disable access", async () => {
    render(<TenantPricingSetup onChanged={changed} />);
    await waitFor(() => expect(screen.getByText("Cloud Compute · Azure")).toBeTruthy());
    fireEvent.click(screen.getByRole("button", { name: /AWS Configured/ }));
    fireEvent.change(screen.getByLabelText("AWS access key ID"), { target: { value: "A".repeat(20) } });
    fireEvent.change(screen.getByLabelText("AWS secret access key"), { target: { value: "B".repeat(40) } });
    fireEvent.click(screen.getByRole("button", { name: "Replace credentials" }));
    await waitFor(() => expect(configureAccess).toHaveBeenCalledWith("aws", { enabled: true, secret: JSON.stringify({ access_key_id: "A".repeat(20), secret_access_key: "B".repeat(40) }) }));
    await waitFor(() => expect(screen.getByText(/Credentials saved. Capture a price/)).toBeTruthy());
    expect((screen.getByLabelText("AWS secret access key") as HTMLInputElement).value).toBe("");
    fireEvent.click(screen.getByRole("button", { name: "Disable pricing access" }));
    await waitFor(() => expect(configureAccess).toHaveBeenLastCalledWith("aws", { enabled: false }));
  });

  it("creates an exact reviewed mapping and approves it separately", async () => {
    render(<TenantPricingSetup onChanged={changed} />);
    await waitFor(() => expect(screen.getByRole("button", { name: "Save draft mapping" }).hasAttribute("disabled")).toBe(false));
    fireEvent.click(screen.getByText("Add Azure mapping"));
    fireEvent.change(screen.getByLabelText("Catalog product"), { target: { value: "product-1" } });
    for (const [label, value] of [["Service", "Virtual Machines"], ["SKU / specification", "Standard_VM"], ["Meter / resource type", "Exact meter"], ["Region", "southeastasia"]]) {
      fireEvent.change(screen.getByLabelText(label), { target: { value } });
    }
    fireEvent.click(screen.getByRole("button", { name: "Save draft mapping" }));
    await waitFor(() => expect(createMapping).toHaveBeenCalledWith({ product_id: "product-1", provider: "azure", service: "Virtual Machines", sku: "Standard_VM", meter: "Exact meter", region: "southeastasia", billing_mode: "pay_per_use" }));
    await waitFor(() => expect(screen.getByRole("button", { name: "Approve mapping" }).hasAttribute("disabled")).toBe(false));
    fireEvent.click(screen.getByRole("button", { name: "Approve mapping" }));
    await waitFor(() => expect(approveMapping).toHaveBeenCalledWith("map-1"));
  });

  it("captures Azure pricing without asking for tenant credentials", async () => {
    render(<TenantPricingSetup onChanged={changed} />);
    await waitFor(() => expect(screen.getByText(/Azure public retail pricing needs no tenant credentials/)).toBeTruthy());
    fireEvent.click(screen.getByRole("button", { name: "Approved mappings" }));
    await waitFor(() => expect(screen.getByRole("button", { name: "Capture price" })).toBeTruthy());
    fireEvent.click(screen.getByRole("button", { name: "Capture price" }));
    await waitFor(() => expect(capture).toHaveBeenCalledWith("map-1"));
    await waitFor(() => expect(changed).toHaveBeenCalled());
  });

  it("captures Huawei dimensions from the approved mapping and explicit usage fields", async () => {
    mappings.mockImplementation((status: string) => Promise.resolve({ items: [{ ...mapping, provider: "huawei", meter: "hws.resource", service: "hws.service", sku: "resource-spec", region: "ap-southeast-5", status }] }));
    render(<TenantPricingSetup onChanged={changed} />);
    fireEvent.click(screen.getByRole("button", { name: "Approved mappings" }));
    await waitFor(() => expect(screen.getByRole("button", { name: "Capture price" }).hasAttribute("disabled")).toBe(false));
    fireEvent.click(screen.getByRole("button", { name: "Capture price" }));
    for (const [label, value] of [["Project ID", "project-1"], ["Usage factor", "Duration"], ["Usage measure ID", "4"], ["Price unit", "hour"]]) {
      fireEvent.change(screen.getByLabelText(label), { target: { value } });
    }
    fireEvent.click(screen.getByRole("button", { name: "Capture Huawei price" }));
    await waitFor(() => expect(capture).toHaveBeenCalledWith("map-1", { market: "intl", project_id: "project-1", cloud_service_type: "hws.service", resource_type: "hws.resource", resource_spec: "resource-spec", region: "ap-southeast-5", usage_factor: "Duration", usage_measure_id: 4, unit: "hour" }));
  });

  it("creates a zero-adjustment policy with explicit currency", async () => {
    render(<TenantPricingSetup onChanged={changed} />);
    await waitFor(() => expect(screen.getByRole("button", { name: "Create list-price policy" }).hasAttribute("disabled")).toBe(false));
    fireEvent.change(screen.getByLabelText("Policy version"), { target: { value: "list-price-v1" } });
    fireEvent.click(screen.getByRole("button", { name: "Create list-price policy" }));
    await waitFor(() => expect(createPolicy).toHaveBeenCalledWith("list-price-v1", "USD"));
    await waitFor(() => expect(changed).toHaveBeenCalled());
  });

  it("shows capture errors and permits retry", async () => {
    capture.mockRejectedValue(new Error("Tenant pricing authorization failed"));
    render(<TenantPricingSetup onChanged={changed} />);
    fireEvent.click(screen.getByRole("button", { name: "Approved mappings" }));
    await waitFor(() => expect(screen.getByRole("button", { name: "Capture price" })).toBeTruthy());
    fireEvent.click(screen.getByRole("button", { name: "Capture price" }));
    await waitFor(() => expect(screen.getByRole("alert").textContent).toContain("Tenant pricing authorization failed"));
    expect(screen.getByRole("button", { name: "Capture price" }).hasAttribute("disabled")).toBe(false);
    expect(changed).not.toHaveBeenCalled();
  });
});
