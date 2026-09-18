import type { DocumentChunk, KnowledgeDocument } from "../types";

const BASE_URL = import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000";

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${BASE_URL}${path}`, init);
  if (!response.ok) {
    let detail = response.statusText;
    try {
      const body = await response.json();
      detail = body.detail ?? detail;
    } catch {
      /* non-JSON error body */
    }
    throw new Error(detail);
  }
  if (response.status === 204) return undefined as T;
  return (await response.json()) as T;
}

export const api = {
  listDocuments: () => request<KnowledgeDocument[]>("/documents"),

  uploadDocument: (file: File) => {
    const form = new FormData();
    form.append("file", file);
    return request<KnowledgeDocument>("/documents", { method: "POST", body: form });
  },

  deleteDocument: (id: string) => request<void>(`/documents/${id}`, { method: "DELETE" }),

  reprocessDocument: (id: string) =>
    request<{ status: string }>(`/documents/${id}/process`, { method: "POST" }),

  listChunks: (id: string) => request<DocumentChunk[]>(`/documents/${id}/chunks?limit=50`),
};
