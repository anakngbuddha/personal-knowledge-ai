// @vitest-environment happy-dom
import React from "react";
import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { McpIntegrationList } from "../types";
import type { PortfolioGraphOut } from "../services/catalog";
import { IntegrationsPanel } from "./IntegrationsPanel";
import { GraphExplorer } from "./GraphExplorer";

const { listMcpIntegrations, upsertMcpIntegration, testMcpIntegration, getPortfolioGraph, listEdges } = vi.hoisted(() => ({
  listMcpIntegrations: vi.fn(),
  upsertMcpIntegration: vi.fn(),
  testMcpIntegration: vi.fn(),
  getPortfolioGraph: vi.fn(),
  listEdges: vi.fn(),
}));

vi.mock("../services/api", () => ({
  api: { listMcpIntegrations, upsertMcpIntegration, testMcpIntegration },
}));

vi.mock("../services/catalog", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../services/catalog")>();
  return {
    ...actual,
    catalogApi: {
      ...actual.catalogApi,
      getPortfolioGraph,
      listEdges,
      getNeighborhood: vi.fn().mockRejectedValue(new Error("not selected")),
    },
  };
});

vi.mock("./MapEditor", () => ({ MapEditor: () => <div>Catalog editor content</div> }));
vi.mock("./ProductImport", () => ({ ProductImport: () => <div>Product import content</div> }));
vi.mock("./CustomMcpStudio", () => ({ CustomMcpStudio: () => <div>Custom MCP setup</div> }));

const connectorData: McpIntegrationList = {
  mcp_enabled: true,
  integrations: [
    { server_slug: "brave", enabled: true, status: "healthy", has_secret: true, allowed_hosts: [], allowed_tools: ["search"] },
    { server_slug: "playwright", enabled: false, status: "disabled", has_secret: false, allowed_hosts: [], allowed_tools: [] },
    { server_slug: "ms365", enabled: true, status: "healthy", has_secret: true, allowed_hosts: [], allowed_tools: ["mail"] },
  ],
};

const graphData: PortfolioGraphOut = {
  nodes: [],
  edges: [],
  categories: [],
  vendors: [],
  relation_types: [],
};

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

describe("Connectors redesign", () => {
  it("filters connector cards by category and search while retaining the custom MCP view", async () => {
    listMcpIntegrations.mockResolvedValue(connectorData);
    render(<IntegrationsPanel />);

    expect(await screen.findByRole("heading", { name: "Connectors" })).toBeTruthy();
    expect(screen.getByRole("heading", { name: "Brave Search" })).toBeTruthy();
    expect(screen.getByRole("heading", { name: "Playwright Browser" })).toBeTruthy();
    expect(screen.getByRole("heading", { name: "Microsoft 365" })).toBeTruthy();

    fireEvent.click(screen.getByRole("button", { name: /^Search$/ }));
    expect(screen.getByRole("heading", { name: "Brave Search" })).toBeTruthy();
    expect(screen.queryByRole("heading", { name: "Microsoft 365" })).toBeNull();

    fireEvent.change(screen.getByRole("textbox", { name: "Search available connectors" }), { target: { value: "brave" } });
    expect(screen.getByRole("heading", { name: "Brave Search" })).toBeTruthy();
    expect(screen.queryByRole("heading", { name: "Playwright Browser" })).toBeNull();

    fireEvent.click(screen.getByRole("button", { name: /Custom MCP Server/ }));
    expect(screen.getByText("Custom MCP setup")).toBeTruthy();
  });

  it("shows connector settings with save and test actions without expanding", async () => {
    listMcpIntegrations.mockResolvedValue(connectorData);
    upsertMcpIntegration.mockResolvedValue(undefined);
    testMcpIntegration.mockResolvedValue({ status: "healthy", tools: [{ name: "search" }] });
    render(<IntegrationsPanel />);

    const heading = await screen.findByRole("heading", { name: "Brave Search" });
    const connector = within(heading.closest("article") as HTMLElement);
    expect(connector.getByPlaceholderText("Stored securely — paste to rotate")).toBeTruthy();
    expect(connector.queryByRole("button", { name: "Brave Search settings" })).toBeNull();

    fireEvent.click(connector.getByRole("button", { name: "Save & Enable" }));
    await waitFor(() => expect(upsertMcpIntegration).toHaveBeenCalledWith("brave", expect.objectContaining({ enabled: true })));

    fireEvent.click(connector.getByRole("button", { name: "Test" }));
    await waitFor(() => expect(testMcpIntegration).toHaveBeenCalledWith("brave"));
  });
});

describe("Knowledge Map redesign", () => {
  it("keeps map controls in a closed drawer and switches between map, catalog, and import views", async () => {
    getPortfolioGraph.mockResolvedValue(graphData);
    listEdges.mockResolvedValue([]);
    render(<GraphExplorer />);

    const views = await screen.findByRole("navigation", { name: "Knowledge Map views" });
    expect(within(views).getByRole("button", { name: "Map" })).toBeTruthy();
    expect(within(views).getByRole("button", { name: "Catalog editor" })).toBeTruthy();
    expect(within(views).getByRole("button", { name: "Import products" })).toBeTruthy();

    const controls = screen.getByRole("complementary", { name: "Map controls" });
    expect(controls.className).toContain("closed");
    fireEvent.click(screen.getByRole("button", { name: "Controls" }));
    await waitFor(() => expect(controls.className).toContain("open"));
    fireEvent.keyDown(window, { key: "Escape" });
    await waitFor(() => expect(controls.className).toContain("closed"));

    fireEvent.click(within(views).getByRole("button", { name: "Catalog editor" }));
    expect(screen.getByText("Catalog editor content")).toBeTruthy();
    fireEvent.click(within(views).getByRole("button", { name: "Import products" }));
    expect(screen.getByText("Product import content")).toBeTruthy();
    expect(screen.getByRole("navigation", { name: "Knowledge Map views" })).toBeTruthy();
  });
});
