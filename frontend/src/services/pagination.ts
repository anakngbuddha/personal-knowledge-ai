export function pageCursor(timestamp: string, id: string): string {
  return btoa(JSON.stringify({ timestamp: new Date(timestamp).toISOString(), id }))
    .replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
}
