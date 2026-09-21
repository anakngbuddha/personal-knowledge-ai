import type { AskResponse, BulkUploadOut, Conversation, ConversationListResponse, DocumentChunk, FreshnessAlert, FreshnessAlertList, FreshnessCheck, KnowledgeDocument, McpIntegration, McpIntegrationList, McpPingResult, NoteList, NoteRecord, PlaybookListResponse, PrincipalProfile, RestoreDrill, RestoreDrillList, RfpAnswerEdit, SearchResponse, SourceMetadata, SsoStatus, VendorSource, VendorSourceList, WorkflowRun, WorkflowRunListResponse } from "../types";
import { request, requestBlob } from "./http";

export const api = {
  login: (email: string, password: string) => 
    request<{access_token:string; role:string}>("/auth/login", {
      method:"POST",
      headers:{"Content-Type":"application/json"},
      body:JSON.stringify({email,password})
    }),
  signup: (body: {email:string; password:string; display_name:string; organization_name:string}) => 
    request<{access_token:string; role:string}>("/auth/signup", {
      method:"POST",
      headers:{"Content-Type":"application/json"},
      body:JSON.stringify(body)
    }),
  listDocuments: (params?: { metadata_complete?: boolean; status?: string }) => {
    const q = new URLSearchParams();
    if(params?.metadata_complete !== undefined) q.set("metadata_complete", String(params.metadata_complete));
    if(params?.status) q.set("status_filter", params.status);
    const s = q.toString();
    return request<KnowledgeDocument[]>(`/documents${s ? `?${s}` : ""}`);
  },
  uploadDocument: (file: File) => {
    const f = new FormData();
    f.append("files", file);
    return request<BulkUploadOut>("/documents", {method:"POST", body:f});
  },
  deleteDocument: (id:string) => request<void>(`/documents/${id}`, {method:"DELETE"}),
  reprocessDocument: (id:string) => request<{status:string}>(`/documents/${id}/process`, {method:"POST"}),
  listChunks: (id:string) => request<DocumentChunk[]>(`/documents/${id}/chunks?limit=50`),
  search: (query:string, options?: {mode?:"hybrid"|"vector"|"keyword"; top_k?:number; filters?:Record<string,unknown>}) =>
    request<SearchResponse>("/search", {
      method:"POST",
      headers:{"Content-Type":"application/json"},
      body:JSON.stringify({query, mode:options?.mode??"hybrid", top_k:options?.top_k??8, filters:options?.filters?? {}})
    }),
  ask: (payload: {question:string; conversation_id?:string|null; exclude_document_ids?:string[]; filters?:Record<string,unknown>; enable_tools?:boolean; strict_mode?:boolean}) =>
    request<AskResponse>("/ask", {
      method:"POST",
      headers:{"Content-Type":"application/json"},
      body:JSON.stringify({...payload, stream:false})
    }),
  listConversations: (limit=20, offset=0) => request<ConversationListResponse>(`/conversations?limit=${limit}&offset=${offset}`),
  getConversation: (id:string) => request<Conversation>(`/conversations/${id}`),
  deleteConversation: (id:string) => request<void>(`/conversations/${id}`, {method:"DELETE"}),
  getConversationSources: (id:string) => request<SourceMetadata[]>(`/conversations/${id}/sources`),
  me: () => request<PrincipalProfile>("/auth/me"),
  listPlaybooks: () => request<PlaybookListResponse>("/playbooks"),
  listWorkflowRuns: (limit=20, offset=0) => request<WorkflowRunListResponse>(`/workflows/runs?limit=${limit}&offset=${offset}`),
  getWorkflowRun: (id:string) => request<WorkflowRun>(`/workflows/runs/${id}`),
  startRfpRun: (file:File, accountRef?:string) => {
    const f = new FormData();
    f.append("file", file);
    if(accountRef) f.append("account_ref", accountRef);
    return request<WorkflowRun>("/workflows/rfp/run", {method:"POST", body:f});
  },
  startSolutionComposer: (notes:string, accountRef?:string) =>
    request<WorkflowRun>("/workflows/solution-composer/run", {
      method:"POST",
      headers:{"Content-Type":"application/json"},
      body:JSON.stringify({notes, account_ref:accountRef||null})
    }),
  startIncidentTriage: (logs:string, installBase:string[]) =>
    request<WorkflowRun>("/workflows/incident-triage/run", {
      method:"POST",
      headers:{"Content-Type":"application/json"},
      body:JSON.stringify({logs, install_base:installBase})
    }),
  startUpgradeImpact: (product:string, proposedVersion?:string) =>
    request<WorkflowRun>("/workflows/upgrade-impact/run", {
      method:"POST",
      headers:{"Content-Type":"application/json"},
      body:JSON.stringify({product, proposed_version:proposedVersion||null})
    }),
  listMcpIntegrations: () => request<McpIntegrationList>("/integrations/mcp"),
  upsertMcpIntegration: (slug:string, body:{enabled:boolean; secret?:string; allowed_hosts?:string[]; http_url?:string|null}) =>
    request<McpIntegration>(`/integrations/mcp/${encodeURIComponent(slug)}`, {
      method:"PUT",
      headers:{"Content-Type":"application/json"},
      body:JSON.stringify(body)
    }),
  testMcpIntegration: (slug:string) => request<McpPingResult>(`/integrations/mcp/${encodeURIComponent(slug)}/test`, {method:"POST"}),
  approveTask: (runId:string, slug:string, answers:RfpAnswerEdit[]) =>
    request<WorkflowRun>(`/workflows/runs/${runId}/tasks/${encodeURIComponent(slug)}/approve", {
      method:"POST",
      headers:{"Content-Type":"application/json"},
      body:JSON.stringify({answers})
    }),
  rejectTask: (runId:string, slug:string, reason:string) =>
    request<WorkflowRun>(`/workflows/runs/${runId}/tasks/${encodeURIComponent(slug)}/reject", {
      method:"POST",
      headers:{"Content-Type":"application/json"},
      body:JSON.stringify({reason})
    }),
  downloadDeliverable: (runId:string) => requestBlob(`/workflows/runs/${runId}/deliverable`),
  listNotes: (limit=50, offset=0) => request<NoteList>(`/notes?limit=${limit}&offset=${offset}`),
  createNote: (body:{title:string; body:string; slug?:string}) =>
    request<NoteRecord>("/notes", {
      method:"POST",
      headers:{"Content-Type":"application/json"},
      body:JSON.stringify(body)
    }),
  updateNote: (id:string, body:{title?:string; body?:string}) =>
    request<NoteRecord>(`/notes/${id}`, {
      method:"PUT",
      headers:{"Content-Type":"application/json"},
      body:JSON.stringify(body)
    }),
  listVendorSources: () => request<VendorSourceList>("/freshness/sources"),
  createVendorSource: (body:{label:string; url:string}) =>
    request<VendorSource>("/freshness/sources", {
      method:"POST",
      headers:{"Content-Type":"application/json"},
      body:JSON.stringify(body)
    }),
  checkVendorSource: (id:string) => request<FreshnessCheck>(`/freshness/sources/${id}/check", {method:"POST"}),
  listFreshnessAlerts: () => request<FreshnessAlertList>("/freshness/alerts"),
  ackFreshnessAlert: (id:string) => request<FreshnessAlert>(`/freshness/alerts/${id}/ack", {method:"POST"}),
  listRestoreDrills: () => request<RestoreDrillList>("/ops/restore-drills"),
  runRestoreDrill: () => request<RestoreDrill>("/ops/restore-drills", {
    method:"POST",
    headers:{"Content-Type":"application/json"},
    body:JSON.stringify({})
  }),
  ssoStatus: () => request<SsoStatus>("/ops/sso")
};
