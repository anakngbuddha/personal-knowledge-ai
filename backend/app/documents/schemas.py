import uuid
from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field


class KeyFactOut(BaseModel):
    """One fact the understand step read out of a source."""

    label: str
    value: str


class DocumentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    original_filename: str
    title: str | None = None
    file_type: str
    file_size: int
    status: str
    page_count: int | None = None
    chunk_count: int = 0

    vendor: str | None = None
    ownership: str = "unknown"
    products_referenced: list[str] | None = None
    account_ref: str | None = None
    approval_state: str = "draft"
    sensitivity: str = "internal"
    valid_until: date | None = None
    source_type: str = "upload"
    source_url: str | None = None
    source_of_truth_url: str | None = None

    # What the understand step read (2.2). A reading of the source, not curated truth.
    summary: str | None = None
    key_facts: list[KeyFactOut] | None = None
    topic_tags: list[str] | None = None
    detected_doc_type: str | None = None
    detected_vendors: list[str] | None = None
    detected_products: list[str] | None = None
    detected_version_label: str | None = None
    understanding_confidence: float | None = None
    understanding_source: str | None = None
    understood_at: datetime | None = None

    metadata_complete: bool = False
    metadata_missing: list[str] | None = None
    version: int = 1
    is_current: bool = True
    supersedes_id: uuid.UUID | None = None
    content_hash: str | None = None
    ocr_applied: bool = False
    injection_flag_count: int = 0

    uploaded_at: datetime | None = None
    processed_at: datetime | None = None
    error_message: str | None = None


class DocumentStatusOut(BaseModel):
    id: uuid.UUID
    status: str
    chunk_count: int
    error_message: str | None = None
    job_status: str | None = None
    attempts: int | None = None


class ChunkOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    chunk_index: int
    page_number: int | None = None
    slide_number: int | None = None
    sheet_name: str | None = None
    cell_range: str | None = None
    section_title: str | None = None
    heading_path: list[str] | None = None
    citation: str | None = None
    start_offset: int | None = None
    end_offset: int | None = None
    text: str
    has_embedding: bool = True
    injection_flags: list[dict] | None = None
    is_table: bool = False
    has_parent_passage: bool = False


class UploadReport(BaseModel):
    """Result of one file in a bulk upload. A partial failure is reported, never fatal."""

    original_filename: str
    status: str  # queued | duplicate | rejected
    document_id: uuid.UUID | None = None
    duplicate_of: uuid.UUID | None = None
    detail: str | None = None


class BulkUploadOut(BaseModel):
    queued: int
    duplicates: int
    rejected: int
    results: list[UploadReport]


class UrlIngestIn(BaseModel):
    url: str = Field(min_length=8, max_length=2048)
    title: str | None = None
    vendor: str | None = None
    ownership: str = "unknown"
    products_referenced: list[str] = Field(default_factory=list)
    account_ref: str | None = None
    approval_state: str = "draft"
    sensitivity: str = "internal"
    valid_until: date | None = None
    source_of_truth_url: str | None = None


class PasteIngestIn(BaseModel):
    text: str = Field(min_length=1)
    title: str = Field(min_length=1, max_length=512)
    vendor: str | None = None
    ownership: str = "unknown"
    products_referenced: list[str] = Field(default_factory=list)
    account_ref: str | None = None
    approval_state: str = "draft"
    sensitivity: str = "internal"
    valid_until: date | None = None
    source_of_truth_url: str | None = None


class ApprovalIn(BaseModel):
    approval_state: str


class MetadataPatchIn(BaseModel):
    title: str | None = None
    vendor: str | None = None
    ownership: str | None = None
    products_referenced: list[str] | None = None
    account_ref: str | None = None
    approval_state: str | None = None
    sensitivity: str | None = None
    valid_until: date | None = None
    source_of_truth_url: str | None = None
    # The understand step writes this once; a person can rewrite it.
    summary: str | None = None
