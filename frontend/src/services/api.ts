import type {
  AskResponse,
  BulkUploadOut,
  Conversation,
  ConversationListResponse,
  DocumentChunk,
  KnowledgeDocument,
  SearchResponse,
  SourceMetadata,
} from "../types";

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
  // ── Phase 1: Documents & Ingestion ──────────────────────────────────────────
  listDocuments: (params?: { metadata_complete?: boolean; status?: string }) => {
    const query = new URLSearchParams();
    if (params?.metadata_complete !== undefined) {
      query.set("metadata_complete", String(params.metadata_complete));
    }
    if (params?.status) {
      query.set("status_filter", params.status);
    }
    const qs = query.toString();
    return request<KnowledgeDocument[]>(`/documents${qs ? `?${qs}` : ""}`);
  },

  uploadDocument: (file: File) => {
    const form = new FormData();
    form.append("files", file); // Backend expects "files" for bulk upload handler
    return request<BulkUploadOut>("/documents", { method: "POST", body: form });
  },

  deleteDocument: (id: string) => request<void>(`/documents/${id}`, { method: "DELETE" }),

  reprocessDocument: (id: string) =>
    request<{ status: string }>(`/documents/${id}/process`, { method: "POST" }),

  listChunks: (id: string) => request<DocumentChunk[]>(`/documents/${id}/chunks?limit=50`),

  // ── Phase 2: Hybrid Retrieval ───────────────────────────────────────────────
  search: (
    query: string,
    options?: {
      mode?: "hybrid" | "vector" | "keyword";
      top_k?: number;
      filters?: {
        products?: string[];
        vendor?: string;
        ownership?: string;
        account_ref?: string;
        approved_only?: boolean;
        exclude_injection_flagged?: boolean;
      };
    }
  ) =>
    request<SearchResponse>("/search", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        query,
        mode: options?.mode ?? "hybrid",
        top_k: options?.top_k ?? 8,
        filters: options?.filters ?? {},
      }),
    }),

  // ── Phase 3: Grounded Answers & Conversations ──────────────────────────────
  ask: (payload: {
    question: string;
    conversation_id?: string | null;
    exclude_document_ids?: string[];
    filters?: {
      products?: string[];
      vendor?: string;
      ownership?: string;
      account_ref?: string;
      approved_only?: boolean;
    };
  }) =>
    request<AskResponse>("/ask", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        question: payload.question,
        conversation_id: payload.conversation_id || null,
        exclude_document_ids: payload.exclude_document_ids || [],
        filters: payload.filters || {},
        stream: false,
      }),
    }),

  listConversations: (limit = 20, offset = 0) =>
    request<ConversationListResponse>(`/conversations?limit=${limit}&offset=${offset}`),

  getConversation: (id: string) => request<Conversation>(`/conversations/${id}`),

  deleteConversation: (id: string) =>
    request<void>(`/conversations/${id}`, { method: "DELETE" }),

  getConversationSources: (id: string) =>
    request<SourceMetadata[]>(`/conversations/${id}/sources`),
};
