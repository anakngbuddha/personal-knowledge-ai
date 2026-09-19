export type DocumentStatus = "uploading" | "uploaded" | "processing" | "ready" | "failed";

export interface KnowledgeDocument {
  id: string;
  original_filename: string;
  file_type: string;
  file_size: number;
  status: DocumentStatus;
  page_count: number | null;
  chunk_count: number;
  uploaded_at: string | null;
  processed_at: string | null;
  error_message: string | null;
}

export interface DocumentChunk {
  id: string;
  chunk_index: number;
  page_number: number | null;
  section_title: string | null;
  start_offset: number | null;
  end_offset: number | null;
  text: string;
  has_embedding: boolean;
}
