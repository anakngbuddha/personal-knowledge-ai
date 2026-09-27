import { describe, expect, it, vi } from "vitest";
import { askWithConversationRecovery } from "./askRecovery";
import { ApiError } from "./http";

describe("stale Ask conversation recovery", () => {
  it("retries once as a new conversation in the selected notebook", async () => {
    const request = vi.fn().mockRejectedValueOnce(new ApiError(404, "Conversation not found"))
      .mockResolvedValueOnce({conversation_id: "new"});
    const clear = vi.fn();
    const result = await askWithConversationRecovery<{conversation_id:string}>("stale", request, () => true, clear);
    expect(result.conversation_id).toBe("new");
    expect(request.mock.calls).toEqual([["stale"], [null]]);
    expect(clear).toHaveBeenCalledOnce();
  });

  it("does not retry after text streamed or the notebook changed", async () => {
    const request = vi.fn().mockRejectedValue(new ApiError(404, "Conversation not found"));
    await expect(askWithConversationRecovery("stale", request, () => false, vi.fn())).rejects.toThrow();
    expect(request).toHaveBeenCalledOnce();
  });

  it("does not erase context on other failures", async () => {
    const request = vi.fn().mockRejectedValue(new ApiError(503, "Provider unavailable"));
    const clear = vi.fn();
    await expect(askWithConversationRecovery("active", request, () => true, clear)).rejects.toThrow();
    expect(clear).not.toHaveBeenCalled();
  });
});
