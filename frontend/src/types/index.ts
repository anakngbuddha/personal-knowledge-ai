export type DocumentStatus = "uploading" | "uploaded" | "processing" | "ready" | "failed";

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
  approval_state?: string | null;
  sensitivity?: string | null;
  valid_until?: string | null;
  metadata_complete: boolean;
  metadata_missing?: string[] | null;
  version: number;
  is_current: boolean;
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
  title?: string | null;
  messages: Message[];
  created_at: string;
  updated_at: string;
}

export interface ConversationListResponse {
  conversations: Conversation[];
  total: number;
  limit: number;
  offset: number;
}
