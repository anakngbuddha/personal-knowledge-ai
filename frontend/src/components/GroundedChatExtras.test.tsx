// @vitest-environment happy-dom
import { cleanup, fireEvent, render } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import {
  ActiveGoalBanner,
  ActiveMentionsBar,
  MentionPalette,
  ProductConnectionsCard,
  QuickActionBar,
  SLASH_COMMANDS,
  SlashPalette,
} from "./GroundedChatExtras";
import type { MentionTarget, ProductConnections } from "../types";

afterEach(cleanup);

it("exports all required slash commands", () => {
  const cmds = SLASH_COMMANDS.map((c) => c.cmd);
  expect(cmds).toContain("/goal");
  expect(cmds).toContain("/connections");
  expect(cmds).toContain("/plan");
  expect(cmds).toContain("/graphify-sync");
  expect(cmds).toContain("/help");
});

it("renders active goal banner and responds to edit and clear", () => {
  const onEdit = vi.fn();
  const onClear = vi.fn();
  const { getByText } = render(
    <ActiveGoalBanner goal="Deploy multi-cloud architecture" onEdit={onEdit} onClear={onClear} />
  );

  expect(getByText("Deploy multi-cloud architecture")).toBeDefined();
  expect(getByText("ACTIVE SESSION GOAL")).toBeDefined();

  fireEvent.click(getByText("Edit"));
  expect(onEdit).toHaveBeenCalledOnce();

  fireEvent.click(getByText("Clear"));
  expect(onClear).toHaveBeenCalledOnce();
});

it("renders product connections card with dependencies and conflict warnings", () => {
  const mockConnections: ProductConnections = {
    product_id: "prod-1",
    product_name: "Atlas-Core",
    vendor: "DeepAtlas",
    category: "Infrastructure",
    prerequisites: [{ id: "p-1", name: "PostgreSQL 16", relation_type: "requires" }],
    conflicts: [{ id: "c-1", name: "Legacy-V1", relation_type: "conflicts_with", evidence: "Incompatible API" }],
    integrations: [{ id: "i-1", name: "Redis Cache", relation_type: "integrates_with" }],
    alternatives: [],
    collateral_count: 3,
  };
  const onNavigateMap = vi.fn();

  const { getByText } = render(
    <ProductConnectionsCard connections={mockConnections} onNavigateMap={onNavigateMap} />
  );

  expect(getByText("Atlas-Core")).toBeDefined();
  expect(getByText("DeepAtlas")).toBeDefined();
  expect(getByText("PostgreSQL 16")).toBeDefined();
  expect(getByText("Legacy-V1")).toBeDefined();
  expect(getByText("Redis Cache")).toBeDefined();

  fireEvent.click(getByText(/Explore in Map/i));
  expect(onNavigateMap).toHaveBeenCalledOnce();
});

it("renders mention palette and handles selection", () => {
  const targets: MentionTarget[] = [
    { id: "note-1", ref: "note:arch", name: "Architecture Note", category: "note", subtitle: "Workspace Note" },
    { id: "prod-1", ref: "product:atlas", name: "Atlas Core", category: "product", subtitle: "Platform" },
  ];
  const onSelectTarget = vi.fn();
  const onSelectCategory = vi.fn();

  const { getByText } = render(
    <MentionPalette
      targets={targets}
      selectedIndex={0}
      category="all"
      onSelectCategory={onSelectCategory}
      onSelectTarget={onSelectTarget}
      loading={false}
    />
  );

  expect(getByText("Architecture Note")).toBeDefined();
  expect(getByText("Atlas Core")).toBeDefined();

  fireEvent.click(getByText("Architecture Note"));
  expect(onSelectTarget).toHaveBeenCalledWith(targets[0]);

  fireEvent.click(getByText("Notes"));
  expect(onSelectCategory).toHaveBeenCalledWith("note");
});

it("renders active mentions bar and handles remove action", () => {
  const mentions: MentionTarget[] = [
    { id: "note-1", ref: "note:security", name: "Security Standards", category: "note" },
    { id: "conn-1", ref: "connector:brave", name: "Brave Search", category: "connector" },
  ];
  const onRemove = vi.fn();

  const { getByText, getByLabelText } = render(
    <ActiveMentionsBar mentions={mentions} onRemoveMention={onRemove} />
  );

  expect(getByText("Security Standards")).toBeDefined();
  expect(getByText("Brave Search")).toBeDefined();

  fireEvent.click(getByLabelText("Remove mention Security Standards"));
  expect(onRemove).toHaveBeenCalledWith("note-1");
});

it("renders quick action bar and triggers commands and mentions", () => {
  const onMention = vi.fn();
  const onSlash = vi.fn();

  const { getByText } = render(
    <QuickActionBar onTriggerMention={onMention} onTriggerSlash={onSlash} />
  );

  fireEvent.click(getByText("📝 Notes"));
  expect(onMention).toHaveBeenCalledWith("note");

  fireEvent.click(getByText("🎯 /goal"));
  expect(onSlash).toHaveBeenCalledWith("/goal ");

  fireEvent.click(getByText("🕸️ /connections"));
  expect(onSlash).toHaveBeenCalledWith("/connections ");
});
