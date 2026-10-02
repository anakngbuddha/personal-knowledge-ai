// @vitest-environment happy-dom
import { cleanup, fireEvent, render, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { GroundedChat } from "./GroundedChat";
import { api } from "../services/api";
import type { Conversation, ProductConnections } from "../types";

vi.mock("../services/api", () => ({api: {
  listConversations: vi.fn(), getConversation: vi.fn(), askStream: vi.fn(), getMentionTargets: vi.fn(),
}}));

let savedGoal: string | null = null;
let savedMessages: Conversation["messages"] = [];
const connections: ProductConnections = {
  product_id: "product-1", product_name: "Atlas Core", vendor: "Atlas", category: "Platform",
  prerequisites: [], conflicts: [], integrations: [], alternatives: [], collateral_count: 1,
};
const conversation = (): Conversation => ({
  id: "conv-1", workspace_id: "workspace-1", title: "Deployment", messages: savedMessages,
  goal: savedGoal, created_at: "2026-10-02T00:00:00Z", updated_at: "2026-10-02T00:00:00Z",
});

beforeEach(() => {
  vi.resetAllMocks();
  savedGoal = null;
  savedMessages = [];
  vi.mocked(api.listConversations).mockResolvedValue({conversations: [], total: 0, limit: 30, offset: 0});
  vi.mocked(api.getConversation).mockImplementation(async () => conversation());
  vi.mocked(api.getMentionTargets).mockResolvedValue([]);
  vi.mocked(api.askStream).mockImplementation(async (payload) => {
    if (payload.question.startsWith("/goal ")) {
      savedGoal = ["/goal clear", "/goal done"].includes(payload.question) ? null : payload.question.slice(6);
    }
    return {answer: "Done", conversation_id: "conv-1", active_goal: savedGoal};
  });
});
afterEach(cleanup);

function openChat() {
  return render(<GroundedChat sourceCount={0} documentIds={[]} onNavigate={vi.fn()} />);
}

it("sets, restores, achieves and clears session goals through the API", async () => {
  const view = openChat();
  const input = view.getByRole("combobox", {name: "Ask a question"}) as HTMLInputElement;
  fireEvent.change(input, {target: {value: "/goal Prepare cloud deployment"}});
  fireEvent.submit(input.closest("form")!);
  await waitFor(() => expect(view.getByText("Prepare cloud deployment")).toBeDefined());
  await waitFor(() => expect(input.disabled).toBe(false));
  fireEvent.change(input, {target: {value: "Preserve my draft"}});
  fireEvent.click(view.getByText("Achieved"));
  await waitFor(() => expect(view.queryByText("ACTIVE SESSION GOAL")).toBeNull());
  expect(vi.mocked(api.askStream).mock.calls[1][0].question).toBe("/goal done");
  expect(input.value).toBe("Preserve my draft");
  await waitFor(() => expect(input.disabled).toBe(false));
  fireEvent.change(input, {target: {value: "/goal Review readiness"}});
  fireEvent.submit(input.closest("form")!);
  await waitFor(() => expect(view.getByText("Review readiness")).toBeDefined());
  await waitFor(() => expect(input.disabled).toBe(false));
  fireEvent.click(view.getByText("Clear"));
  await waitFor(() => expect(view.queryByText("ACTIVE SESSION GOAL")).toBeNull());
  const calls = vi.mocked(api.askStream).mock.calls;
  expect(calls[calls.length - 1][0].question).toBe("/goal clear");
});

it("inserts a mention at the cursor without deleting the rest of the question", async () => {
  const target = {id: "note-1", ref: "note:Deployment Plan", name: "Deployment Plan", category: "note" as const};
  vi.mocked(api.getMentionTargets).mockResolvedValue([target]);
  const view = openChat();
  const input = view.getByRole("combobox", {name: "Ask a question"}) as HTMLInputElement;
  fireEvent.change(input, {target: {value: "Compare @at with Cloud", selectionStart: 11}});
  await waitFor(() => expect(view.getByRole("option", {name: /Deployment Plan/})).toBeDefined());
  expect(api.getMentionTargets).toHaveBeenCalledWith("at", undefined, 15);
  fireEvent.keyDown(input, {key: "Enter"});
  expect(input.value).toBe('Compare @note:"Deployment Plan"  with Cloud');
  expect(view.getByLabelText("Remove mention Deployment Plan")).toBeDefined();
  fireEvent.change(input, {target: {value: "Compare with Cloud"}});
  expect(view.queryByLabelText("Remove mention Deployment Plan")).toBeNull();
  fireEvent.submit(input.closest("form")!);
  await waitFor(() => expect(api.askStream).toHaveBeenCalled());
  expect(vi.mocked(api.askStream).mock.calls[0][0].question).toBe("Compare with Cloud");
});

it("opens both palettes with quick actions and dismisses an empty palette with Escape", async () => {
  const view = openChat();
  const input = view.getByRole("combobox", {name: "Ask a question"}) as HTMLInputElement;
  fireEvent.click(view.getByText("@ Mention"));
  expect(view.getByRole("listbox", {name: "Mention targets"})).toBeDefined();
  fireEvent.keyDown(input, {key: "Escape"});
  expect(view.queryByRole("listbox", {name: "Mention targets"})).toBeNull();
  fireEvent.click(view.getByText("/ Commands"));
  expect(view.getByRole("listbox", {name: "Commands"})).toBeDefined();
  fireEvent.keyDown(input, {key: "ArrowDown"});
  fireEvent.keyDown(input, {key: "Enter"});
  expect(input.value).toBe("/connections ");
  expect(view.queryByRole("listbox", {name: "Commands"})).toBeNull();
});

it("restores the goal and connection card when opening a saved conversation", async () => {
  savedGoal = "Assess Atlas";
  savedMessages = [{id: "message-1", role: "assistant", content: "Product relationships", citations: [],
    sources: [], refused: false, created_at: "2026-10-02T00:00:00Z", connections_result: connections}];
  vi.mocked(api.listConversations).mockResolvedValue({conversations: [conversation()], total: 1, limit: 30, offset: 0});
  const view = openChat();
  fireEvent.click(view.getByRole("button", {name: /history/i}));
  await waitFor(() => expect(view.getByText("Deployment")).toBeDefined());
  fireEvent.click(view.getByText("Deployment"));
  await waitFor(() => expect(view.getByText("Assess Atlas")).toBeDefined());
  expect(view.getByText("Atlas Core")).toBeDefined();
  fireEvent.click(view.getByRole("button", {name: "New session"}));
  expect(view.queryByText("ACTIVE SESSION GOAL")).toBeNull();
});
