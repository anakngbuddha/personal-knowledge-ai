import type {
  AskResponse,
  BulkUploadOut,
  Conversation,
  ConversationListResponse,
  DocumentChunk,
  KnowledgeDocument,
  PlaybookListResponse,
  PrincipalProfile,
  RfpAnswerEdit,
  SearchResponse,
  SourceMetadata,
  WorkflowRun,
  WorkflowRunListResponse,
} from "../types";
import { request, requestBlob } from "./http";

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

  me: () => request<PrincipalProfile>("/auth/me"),

  listPlaybooks: () => request<PlaybookListResponse>("/playbooks"),

  listWorkflowRuns: (limit = 20, offset = 0) =>
    request<WorkflowRunListResponse>(`/workflows/runs?limit=${limit}&offset=${offset}`),

  getWorkflowRun: (id: string) => request<WorkflowRun>(`/workflows/runs/${id}`),

  startRfpRun: (file: File, accountRef?: string) => {
    const form = new FormData();
    form.append("file", file);
    if (accountRef) form.append("account_ref", accountRef);
    return request<WorkflowRun>("/workflows/rfp/run", { method: "POST", body: form });
  },

  approveTask: (runId: string, slug: string, answers: RfpAnswerEdit[]) =>
    request<WorkflowRun>(`/workflows/runs/${runId}/tasks/${encodeURIComponent(slug)}/approve`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ answers }),
    }),

  rejectTask: (runId: string, slug: string, reason: string) =>
    request<WorkflowRun>(`/workflows/runs/${runId}/tasks/${encodeURIComponent(slug)}/reject`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ reason }),
    }),

  downloadDeliverable: (runId: string) => requestBlob(`/workflows/runs/${runId}/deliverable`),
};
