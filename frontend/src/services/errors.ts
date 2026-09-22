/** One sentence a salesperson can act on. Technical detail stays off the screen. */

const UUID_RE = /[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}/i;

export function friendlyError(status: number, detail: string): string {
  const text = (detail || "").replace(/\s+/g, " ").trim();
  const plain =
    text.length > 0 &&
    text.length < 180 &&
    !UUID_RE.test(text) &&
    !/select |insert |traceback|exception|\bsql\b|\{|\[/i.test(text);

  if (status === 401) return "Your session expired. Please sign in again.";
  if (status === 403) return plain ? text : "You do not have permission to do that.";
  if (status === 404) return plain ? text : "That item is not available.";
  if (status === 409) return plain ? text : "That name is already in use.";
  if (status === 429) return "The server is busy. Wait a moment and try again.";
  if (status === 400) return plain ? text : "Check the fields and try again.";
  if (status >= 500) return "Something went wrong. Try again in a moment.";
  return plain ? text : "Something went wrong. Try again.";
}

export const SERVER_WAKING = "Waking the server, ~30 seconds";
export const SERVER_ASLEEP = "The server did not wake up. Try again.";
