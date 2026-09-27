import type { AskResponse, BulkUploadOut, Conversation, ConversationListResponse, DocumentChunk, DocumentStatusReport, FreshnessAlert, FreshnessAlertList, FreshnessCheck, GraphEdge, KnowledgeDocument, LinkTargetOut, McpExecuteResult, McpIntegration, McpIntegrationList, McpPingResult, McpServerConfig, McpServerStatus, NoteGraphOut, NoteList, NoteRecord, NotebookList, NotebookRecord, NotebookSource, PlaybookListResponse, PrincipalProfile, RestoreDrill, RestoreDrillList, RfpAnswerEdit, SearchResponse, SourceMetadata, SsoStatus, StudioResult, VendorSource, VendorSourceList, WorkflowRun, WorkflowRunListResponse } from "../types";
import { fetchResponse, request, requestBlob } from "./http";

type AuthTokenResponse = { access_token: string; role: string; expires_in_seconds: number };

export const api = {
  login: (email: string, password: string) => 
    request<AuthTokenResponse>("/auth/login", {
      method:"POST",
      headers:{"Content-Type":"application/json"},
      body:JSON.stringify({email,password})
    }),
  signup: (body: {email:string; password:string; display_name:string; organization_name:string}) => 
    request<AuthTokenResponse>("/auth/signup", {
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
  getDocument: (id:string) => request<KnowledgeDocument>(`/documents/${id}`),
  uploadDocument: (file: File) => {
    const f = new FormData();
    f.append("files", file);
    return request<BulkUploadOut>("/documents", {method:"POST", body:f});
  },
  /** Many files (or a whole folder drop) in one request. One bad file never sinks the batch. */
  uploadDocuments: (files: File[], shared?: {vendor?:string; account_ref?:string}) => {
    const f = new FormData();
    files.forEach((file) => f.append("files", file));
    if(shared?.vendor) f.append("vendor", shared.vendor);
    if(shared?.account_ref) f.append("account_ref", shared.account_ref);
    return request<BulkUploadOut>("/documents", {method:"POST", body:f});
  },
  documentStatus: (id:string) => request<DocumentStatusReport>(`/documents/${id}/status`),
  updateDocument: (id:string, body:{title?:string|null; vendor?:string|null; products_referenced?:string[]|null; valid_until?:string|null; summary?:string|null; account_ref?:string|null; ownership?:string|null}) =>
    request<KnowledgeDocument>(`/documents/${id}`, {
      method:"PATCH",
      headers:{"Content-Type":"application/json"},
      body:JSON.stringify(body)
    }),
  deleteDocument: (id:string) => request<void>(`/documents/${id}`, {method:"DELETE"}),
  reprocessDocument: (id:string) => request<{status:string}>(`/documents/${id}/process`, {method:"POST"}),
  listChunks: (id:string) => request<DocumentChunk[]>(`/documents/${id}/chunks?limit=50`),
  search: (query:string, options?: {mode?:"hybrid"|"vector"|"keyword"; top_k?:number; filters?:Record<string,unknown>}) =>
    request<SearchResponse>("/search", {
      method:"POST",
      headers:{"Content-Type":"application/json"},
      body:JSON.stringify({query, mode:options?.mode??"hybrid", top_k:options?.top_k??8, filters:options?.filters?? {}})
    }),
  ask: (payload: {question:string; conversation_id?:string|null; notebook_id?:string|null; exclude_document_ids?:string[]; filters?:Record<string,unknown>; enable_tools?:boolean; strict_mode?:boolean; web_search?:boolean}) =>
    request<AskResponse>("/ask", {
      method:"POST",
      headers:{"Content-Type":"application/json"},
      body:JSON.stringify({...payload, stream:false})
    }),
  saveWebSource: (body: {url: string; title?: string | null; notebook_id?: string | null}) =>
    request<{document_id: string; notebook_id?: string | null}>("/ask/web-sources", {
      method: "POST",
      headers: {"Content-Type":"application/json"},
      body: JSON.stringify(body)
    }),
  askStream: async (
    payload: {question:string; conversation_id?:string|null; notebook_id?:string|null; exclude_document_ids?:string[]; filters?:Record<string,unknown>; enable_tools?:boolean; strict_mode?:boolean; web_search?:boolean},
    onDelta: (text: string) => void,
    onStatus?: (status: string) => void
  ): Promise<Partial<AskResponse>> => {
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), 120000);
    try {
      const res = await fetchResponse("/ask", {
        method: "POST",
        headers: {"Content-Type":"application/json"},
        body: JSON.stringify({...payload, stream: true}),
        signal: controller.signal
      }, 120000);
      if (!res.body) throw new Error("No response from the server");
      const reader = res.body.getReader();
      const decoder = new TextDecoder();
      let buffer = "";
      let assembled = "";
      let donePayload: Partial<AskResponse> = {answer: ""};
      while (true) {
        const {value, done} = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, {stream: true});
        const blocks = buffer.split("\n\n");
        buffer = blocks.pop() ?? "";
        for (const block of blocks) {
          const line = block.split("\n").find((l) => l.startsWith("data: "));
          if (!line) continue;
          const data = line.slice(6).trim();
          if (data === "[DONE]") continue;
          const event = JSON.parse(data) as {delta?: string; done?: boolean; error?: string; status?: string; citations?: SourceMetadata[]; conversation_id?: string; message_id?: string; refused?: boolean; web_note?: string | null; web_sources?: SourceMetadata[]};
          if (event.error) throw new Error(event.error);
          if (event.status) onStatus?.(event.status);
          if (event.delta) {
            assembled += event.delta;
            onDelta(assembled);
          }
          if (event.done) {
            donePayload = {
              answer: assembled,
              citations: event.citations || [],
              conversation_id: event.conversation_id,
              message_id: event.message_id,
              refused: Boolean(event.refused),
              web_note: event.web_note,
              web_sources: event.web_sources || []
            };
          }
        }
      }
      return donePayload;
    } finally {
      clearTimeout(timer);
    }
  },
  listConversations: (limit=20, offset=0, notebookId?: string) => {
    const q = new URLSearchParams({ limit: String(limit), offset: String(offset) });
    if (notebookId) q.set("notebook_id", notebookId);
    return request<ConversationListResponse>(`/conversations?${q}`);
  },
  getConversation: (id:string) => request<Conversation>(`/conversations/${id}`),
  deleteConversation: (id:string) => request<void>(`/conversations/${id}`, {method:"DELETE"}),
  getConversationSources: (id:string) => request<SourceMetadata[]>(`/conversations/${id}/sources`),
  me: () => request<PrincipalProfile>("/auth/me"),
  listPlaybooks: () => request<PlaybookListResponse>("/playbooks"),
  listEdges: (params?: {status?:string; relation_type?:string; product_id?:string}) => {
    const q = new URLSearchParams();
    if(params?.status) q.set("status", params.status);
    if(params?.relation_type) q.set("relation_type", params.relation_type);
    if(params?.product_id) q.set("product_id", params.product_id);
    const s = q.toString();
    return request<GraphEdge[]>(`/graph/edges${s ? `?${s}` : ""}`);
  },
  approveEdge: (id:string) => request<GraphEdge>(`/graph/edges/${id}/approve`, {method:"POST"}),
  rejectEdge: (id:string, reason:string) =>
    request<GraphEdge>(`/graph/edges/${id}/reject`, {
      method:"POST",
      headers:{"Content-Type":"application/json"},
      body:JSON.stringify({reason})
    }),
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
    request<WorkflowRun>(`/workflows/runs/${runId}/tasks/${encodeURIComponent(slug)}/approve`, {
      method:"POST",
      headers:{"Content-Type":"application/json"},
      body:JSON.stringify({answers})
    }),
  rejectTask: (runId:string, slug:string, reason:string) =>
    request<WorkflowRun>(`/workflows/runs/${runId}/tasks/${encodeURIComponent(slug)}/reject`, {
      method:"POST",
      headers:{"Content-Type":"application/json"},
      body:JSON.stringify({reason})
    }),
  downloadDeliverable: (runId:string) => requestBlob(`/workflows/runs/${runId}/deliverable`),
  listNotes: (limit=50, offset=0, notebookId?: string) => {
    const q = new URLSearchParams({ limit: String(limit), offset: String(offset) });
    if (notebookId) q.set("notebook_id", notebookId);
    return request<NoteList>(`/notes?${q}`);
  },
  createNote: (body:{title:string; body:string; slug?:string; notebook_id?:string}) =>
    request<NoteRecord>("/notes", {
      method:"POST",
      headers:{"Content-Type":"application/json"},
      body:JSON.stringify(body)
    }),
  listNotebooks: () => request<NotebookList>("/notebooks?limit=100"),
  createNotebook: (name: string) =>
    request<NotebookRecord>("/notebooks", {
      method: "POST",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify({ name }),
    }),
  renameNotebook: (id: string, name: string) =>
    request<NotebookRecord>(`/notebooks/${id}`, {
      method: "PATCH",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify({ name }),
    }),
  deleteNotebook: (id: string) => request<void>(`/notebooks/${id}`, { method: "DELETE" }),
  listNotebookSources: (id: string) => request<NotebookSource[]>(`/notebooks/${id}/sources`),
  setNotebookSources: (id: string, documentIds: string[]) =>
    request<NotebookSource[]>(`/notebooks/${id}/sources`, {
      method: "PUT",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify({ document_ids: documentIds }),
    }),
  studioQuestions: (documentId: string) =>
    request<{ document_id: string; questions: string[] }>(`/studio/questions?document_id=${documentId}`),
  studioRun: (body: { kind: "briefing" | "faq" | "compare"; document_ids: string[]; notebook_id?: string | null; save_as_note?: boolean }) =>
    request<StudioResult>("/studio/run", {
      method: "POST",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify(body),
    }),
  updateNote: (id:string, body:{title?:string; body?:string}) =>
    request<NoteRecord>(`/notes/${id}`, {
      method:"PUT",
      headers:{"Content-Type":"application/json"},
      body:JSON.stringify(body)
    }),
  deleteNote: (id: string) => request<void>(`/notes/${id}`, { method: "DELETE" }),
  listVendorSources: () => request<VendorSourceList>("/freshness/sources"),
  createVendorSource: (body:{label:string; url:string}) =>
    request<VendorSource>("/freshness/sources", {
      method:"POST",
      headers:{"Content-Type":"application/json"},
      body:JSON.stringify(body)
    }),
  checkVendorSource: (id:string) => request<FreshnessCheck>(`/freshness/sources/${id}/check`, {method:"POST"}),
  listFreshnessAlerts: () => request<FreshnessAlertList>("/freshness/alerts"),
  ackFreshnessAlert: (id:string) => request<FreshnessAlert>(`/freshness/alerts/${id}/ack`, {method:"POST"}),
  listRestoreDrills: () => request<RestoreDrillList>("/ops/restore-drills"),
  runRestoreDrill: () => request<RestoreDrill>("/ops/restore-drills", {
    method:"POST",
    headers:{"Content-Type":"application/json"},
    body:JSON.stringify({})
  }),
  ssoStatus: () => request<SsoStatus>("/ops/sso"),
  getNotesGraph: () => request<NoteGraphOut>("/notes/graph"),
  autocompleteWikilinks: (q: string) => request<LinkTargetOut[]>(`/notes/link-targets?q=${encodeURIComponent(q)}`),
  getBacklinks: (kind: string, ref: string) => request<NoteList>(`/notes/by-link/${encodeURIComponent(kind)}/${encodeURIComponent(ref)}`),
  healthDependencies: () =>
    request<{
      ok: boolean;
      checks: Record<
        string,
        {
          ok?: boolean;
          queued?: number;
          counts?: Record<string, number>;
          worker_in_process?: boolean;
          provider?: string;
          error?: string;
          [key: string]: unknown;
        }
      >;
    }>("/health/dependencies"),
  getCustomMcpStatus: () => request<McpServerStatus>("/api/mcp/custom-server/status"),
  getCustomMcpConfig: () => request<McpServerConfig>("/api/mcp/custom-server/config"),
  generateMcpToken: (role?: string, expires_minutes?: number) =>
    request<{ token: string; server_name: string; expires_minutes: number }>("/api/mcp/custom-server/tokens", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ role: role ?? "solutions_engineer", expires_minutes: expires_minutes ?? 43200 }),
    }),
  executeMcpTool: (name: string, args: Record<string, unknown>) =>
    request<McpExecuteResult>("/api/mcp/custom-server/execute", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ name, arguments: args }),
    }),
};
