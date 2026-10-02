import type { MentionTarget } from "../types";

export function mentionToken(target: MentionTarget): string {
  const split = target.ref.indexOf(":");
  const kind = target.ref.slice(0, split);
  const ref = target.ref.slice(split + 1);
  return `@${kind}:${/\s/.test(ref) && !ref.startsWith('"') ? `"${ref}"` : ref}`;
}

export function mentionAtCaret(text: string, caret: number) {
  const prefix = text.slice(0, caret);
  const match = /(?:^|\s)@([^\s@"]*)$/.exec(prefix);
  if (!match) return null;
  const start = caret - match[1].length - 1;
  const rest = /^[^\s]*/.exec(text.slice(caret))?.[0] || "";
  return { start, end: caret + rest.length, query: match[1] };
}
