import { ApiError } from "./http";

/** Retry only a stale conversation lookup before any answer text was shown. */
export async function askWithConversationRecovery<T>(
  conversationId: string | null,
  request: (id: string | null) => Promise<T>,
  canRetry: () => boolean,
  onStale: () => void,
): Promise<T> {
  try {
    return await request(conversationId);
  } catch (error) {
    if (!(conversationId && canRetry() && error instanceof ApiError && error.status === 404 &&
      error.detail.toLowerCase().includes("conversation not found"))) throw error;
    onStale();
    return request(null);
  }
}
