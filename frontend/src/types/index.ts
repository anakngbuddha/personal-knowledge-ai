export type DocumentStatus =
  | "uploading"
  | "uploaded"
  | "processing"
  | "ready"
  | "failed"
  | "quarantined";

/** One fact the understand step pulled out of a source. */
export interface DocumentKeyFact {
  label: string;
  value: string;
}

export interface KnowledgeDocument {
  id: string;
  original_filename: string;
  title?: string | null;
  file_type: string;
  file_size: number;
  status: DocumentStatus;
  page_count: number | null;
  chunk_count: number;
  uploaded_at: string | null;
  processed_at: string | null;
  error_message: string | null;
  vendor?: string | null;
  ownership?: string | null;
  products_referenced?: string[] | null;
  approval_state?: string | null;
  sensitivity?: string | null;
  valid_until?: string | null;
  ocr_applied?: boolean;
  metadata_complete: boolean;
  metadata_missing?: string[] | null;
  version: number;
  is_current: boolean;

  // What the understand step read out of the source (2.2).
  summary?: string | null;
  key_facts?: DocumentKeyFact[] | null;
  topic_tags?: string[] | null;
  detected_doc_type?: string | null;
  detected_vendors?: string[] | null;
  detected_products?: string[] | null;
  detected_version_label?: string | null;
  understanding_confidence?: number | null;
  understood_at?: string | null;
}

/** Plain-language state of one file while it is being added. */
export type UploadPhase = "queued" | "reading" | "understanding" | "ready" | "failed";

export interface TrackedUpload {
  key: string;
  filename: string;
  file: File;
  phase: UploadPhase;
  documentId?: string | null;
  detail?: string | null;
}

export interface DocumentStatusReport {
  id: string;
  status: DocumentStatus;
  chunk_count: number;
  error_message?: string | null;
  job_status?: string | null;
  attempts?: number | null;
}

export interface DocumentChunk {
  id: string;
  chunk_index: number;
  page_number: number | null;
  slide_number?: number | null;
  sheet_name?: string | null;
  cell_range?: string | null;
  section_title: string | null;
  heading_path?: string[] | null;
  citation?: string | null;
  start_offset: number | null;
  end_offset: number | null;
  text: string;
  has_embedding: boolean;
  injection_flags?: Record<string, unknown>[] | null;
}

export interface UploadReport {
  original_filename: string;
  status: "queued" | "duplicate" | "rejected";
  document_id?: string | null;
  duplicate_of?: string | null;
  detail?: string | null;
}

export interface BulkUploadOut {
  queued: number;
  duplicates: number;
  rejected: number;
  results: UploadReport[];
}

export interface SearchHit {
  chunk_id: string;
  document_id: string;
  document_title?: string | null;
  original_filename: string;
  file_type: string;
  chunk_index: number;
  text: string;
  citation: string;
  page_number?: number | null;
  slide_number?: number | null;
  sheet_name?: string | null;
  cell_range?: string | null;
  section_title?: string | null;
  heading_path: string[];
  vendor?: string | null;
  ownership?: string | null;
  approval_state?: string | null;
  sensitivity?: string | null;
  valid_until?: string | null;
  is_stale: boolean;
  injection_flagged: boolean;
  rrf_score: number;
  ranks: Record<string, number>;
  branch_scores: Record<string, number>;
}

export interface SearchResponse {
  query: string;
  mode: "hybrid" | "vector" | "keyword";
  top_k: number;
  candidate_k: number;
  rrf_k: number;
  candidate_count: number;
  hits: SearchHit[];
  timings_ms: Record<string, number>;
  principal: Record<string, unknown>;
}

export interface SourceMetadata {
  chunk_id: string;
  document_id: string;
  document_title?: string | null;
  citation: string;
  page_number?: number | null;
  slide_number?: number | null;
  sheet_name?: string | null;
  cell_range?: string | null;
  heading_path: string[];
  vendor?: string | null;
  ownership?: string | null;
  approval_state?: string | null;
  sensitivity?: string | null;
  valid_until?: string | null;
  is_stale: boolean;
}

export interface TokenUsage {
  prompt_tokens: number;
  completion_tokens: number;
  total_tokens: number;
}

export interface ToolCallInfo {
  id: string;
  name: string;
  arguments?: Record<string, unknown>;
  error?: string | null;
  content?: Record<string, unknown> | null;
}

export interface AskResponse {
  answer: string;
  citations: SourceMetadata[];
  model_id: string;
  prompt_version: string;
  refused: boolean;
  refusal_reason?: string | null;
  usage?: TokenUsage | null;
  conversation_id?: string | null;
  message_id?: string | null;
  tool_calls?: ToolCallInfo[];
}

export interface Message {
  id: string;
  role: "user" | "assistant" | "system";
  content: string;
  citations: SourceMetadata[];
  sources: SourceMetadata[];
  usage?: TokenUsage | null;
  prompt_version?: string | null;
  refused: boolean;
  model_id?: string | null;
  created_at: string;
}

export interface Conversation {
  id: string;
  workspace_id: string;
  notebook_id?: string | null;
  title?: string | null;
  messages: Message[];
  created_at: string;
  updated_at: string;
}

export interface NotebookRecord {
  id: string;
  name: string;
  workspace_id: string;
  created_at?: string | null;
  updated_at?: string | null;
}

export interface NotebookList {
  notebooks: NotebookRecord[];
  total: number;
  limit: number;
  offset: number;
}

export interface NotebookSource {
  document_id: string;
  title?: string | null;
  filename: string;
  enabled: boolean;
  status: string;
}

export interface StudioResult {
  markdown: string;
  source_titles: string[];
  note_id?: string | null;
}

export interface ConversationListResponse {
  conversations: Conversation[];
  total: number;
  limit: number;
  offset: number;
}

export type TaskStatus =
  | "pending"
  | "running"
  | "waiting_approval"
  | "succeeded"
  | "failed";

export type WorkflowRunStatus = TaskStatus;

export interface PrincipalProfile {
  org_id: string;
  organization_name?: string;
  user_id: string | null;
  role: string;
  can_write_catalog: boolean;
  can_export_restricted?: boolean;
  is_owner?: boolean;
  is_admin?: boolean;
}

export interface Playbook {
  slug: string;
  name: string;
  version: string;
  task_count: number;
  runnable: boolean;
}

export interface PlaybookListResponse {
  playbooks: Playbook[];
}

export interface TaskCounts {
  pending: number;
  running: number;
  waiting_approval: number;
  succeeded: number;
  failed: number;
}

export interface WorkflowRunSummary {
  id: string;
  playbook_slug: string;
  status: WorkflowRunStatus;
  created_at: string;
  updated_at: string;
  error_message?: string | null;
  task_counts: TaskCounts;
}

export interface WorkflowRunListResponse {
  runs: WorkflowRunSummary[];
  total: number;
  limit: number;
  offset: number;
}

export interface ProductImpactHint {
  all_incompatibilities?: Array<{ conflicted_product_name?: string }>;
  all_prerequisites?: Array<{ name?: string }>;
}

export interface CandidateProduct {
  name?: string;
  slug?: string;
  vendor?: string;
  impact?: ProductImpactHint;
}

export interface RfpAnswer {
  id?: string;
  text?: string;
  section?: string;
  must_have?: boolean;
  status?: string;
  confidence?: number;
  response?: string;
  citations?: string[];
  products?: string[];
  unmet_prerequisites?: boolean;
  needs_review?: boolean;
  evidence?: Array<{ citation?: string; text?: string }>;
  candidate_products?: CandidateProduct[];
}

export interface RfpAnswerEdit {
  id: string;
  response?: string;
  status?: string;
}

export interface WorkflowTask {
  id: string;
  slug: string;
  status: TaskStatus;
  depends_on_slugs: string[];
  output_payload?: Record<string, unknown> | null;
  error_message?: string | null;
  retry_count: number;
  max_attempts?: number;
  worker_id?: string | null;
  updated_at?: string | null;
  log_line?: string | null;
}

export interface WorkflowRun {
  id: string;
  playbook_slug: string;
  status: WorkflowRunStatus;
  org_id: string;
  workspace_id: string;
  input_payload?: Record<string, unknown> | null;
  error_message?: string | null;
  tasks: WorkflowTask[];
  created_at: string;
  updated_at: string;
}

/** One relationship on the product map. */
export interface GraphEdge {
  id: string;
  source_product_id: string;
  source_product_name: string;
  target_product_id: string;
  target_product_name: string;
  relation_type: string;
  evidence: string;
  confidence: number;
  document_id?: string | null;
  is_ai_suggested: boolean;
  status: string;
  rejection_reason?: string | null;
  created_at?: string | null;
}

export interface McpIntegration {
  id?: string | null;
  server_slug: string;
  enabled: boolean;
  status: string;
  last_error?: string | null;
  has_secret: boolean;
  allowed_hosts: string[];
  http_url?: string | null;
  allowed_tools: string[];
}

export interface McpIntegrationList {
  mcp_enabled: boolean;
  integrations: McpIntegration[];
}

export interface McpPingResult {
  server: string;
  status: string;
  tools: string[];
}

export interface NoteLink {
  target_kind: string;
  target_ref: string;
  display_text?: string | null;
  resolved: boolean;
  resolved_id?: string | null;
}

export interface NoteRecord {
  id: string;
  title: string;
  slug: string;
  body: string;
  workspace_id: string;
  notebook_id?: string | null;
  created_by?: string | null;
  created_at?: string | null;
  updated_at?: string | null;
  links: NoteLink[];
}

export interface NoteList {
  notes: NoteRecord[];
  total: number;
  limit: number;
  offset: number;
}

export interface VendorSource {
  id: string;
  label: string;
  url: string;
  status: string;
  enabled: boolean;
  last_hash?: string | null;
  last_checked_at?: string | null;
  next_check_at?: string | null;
  last_error?: string | null;
  product_id?: string | null;
}

export interface VendorSourceList {
  sources: VendorSource[];
  total: number;
  limit: number;
  offset: number;
}

export interface FreshnessAlert {
  id: string;
  vendor_source_id: string;
  kind: string;
  previous_hash?: string | null;
  new_hash?: string | null;
  created_at?: string | null;
  acknowledged_at?: string | null;
}

export interface FreshnessAlertList {
  alerts: FreshnessAlert[];
  total: number;
  limit: number;
  offset: number;
}

export interface FreshnessCheck {
  source_id: string;
  status: string;
  hash?: string | null;
  changed: boolean;
  alert_id?: string | null;
  error?: string | null;
}

export interface RestoreDrill {
  id: string;
  status: string;
  sla_seconds: number;
  duration_seconds?: number | null;
  within_sla?: boolean | null;
  error_message?: string | null;
  started_at?: string | null;
  finished_at?: string | null;
}

export interface RestoreDrillList {
  drills: RestoreDrill[];
  total: number;
  limit: number;
  offset: number;
}

export interface SsoStatus {
  sso_enabled: boolean;
  oidc_configured: boolean;
  saml_configured: boolean;
  oidc_issuer?: string | null;
  saml_issuer?: string | null;
  oidc_client_id?: string | null;
}

export interface NoteGraphNode {
  id: string;
  kind: string;
  title: string;
  slug: string;
}

export interface NoteGraphEdge {
  source_id: string;
  source_kind: string;
  target_id: string;
  target_kind: string;
  target_ref: string;
  display_text?: string | null;
  resolved: boolean;
}

export interface NoteGraphOut {
  nodes: NoteGraphNode[];
  edges: NoteGraphEdge[];
}

export interface LinkTargetOut {
  kind: string;
  ref: string;
  title: string;
}

