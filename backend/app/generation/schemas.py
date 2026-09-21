"""Pydantic schemas for the Phase 3 generation API.

All request/response models for the /ask and /conversations endpoints.
Every answer carries structured citations with provenance metadata so the
frontend can render freshness, approval state, and vendor inline.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class SourceMetadataOut(BaseModel):
    """One cited source in an answer, with full provenance."""

    chunk_id: str
    document_id: str
    document_title: str | None = None
    citation: str
    page_number: int | None = None
    slide_number: int | None = None
    sheet_name: str | None = None
    cell_range: str | None = None
    heading_path: list[str] = Field(default_factory=list)
    vendor: str | None = None
    ownership: str | None = None
    approval_state: str | None = None
    sensitivity: str | None = None
    valid_until: str | None = None
    is_stale: bool = False


class TokenUsageOut(BaseModel):
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int


class AskFiltersIn(BaseModel):
    """Optional retrieval filters for the generation endpoint."""

    model_config = ConfigDict(extra="forbid")

    products: list[str] = Field(default_factory=list)
    vendor: str | None = None
    ownership: str | None = None
    account_ref: str | None = None
    approved_only: bool = True  # Default: customer-facing uses approved only
    exclude_injection_flagged: bool = True
    document_ids: list[str] = Field(default_factory=list)


class ToolCallOut(BaseModel):
    """One tool invocation the model requested (and the backend executed)."""

    id: str
    name: str
    arguments: dict = Field(default_factory=dict)
    error: str | None = None
    content: dict | None = None


class AskIn(BaseModel):
    """Request body for POST /ask and POST /conversations/{id}/ask."""

    model_config = ConfigDict(extra="forbid")

    question: str = Field(min_length=1, max_length=4000)
    conversation_id: str | None = None
    filters: AskFiltersIn = Field(default_factory=AskFiltersIn)
    stream: bool = False
    # Source toggling: exclude specific documents from context
    exclude_document_ids: list[str] = Field(default_factory=list)
    enable_tools: bool = False
    # Knowledge mode: False = expert (sources + general knowledge), True = strict (sources only)
    strict_mode: bool = False


class AskOut(BaseModel):
    """Response for a grounded answer."""

    answer: str
    citations: list[SourceMetadataOut]
    model_id: str
    prompt_version: str
    refused: bool = False
    refusal_reason: str | None = None
    usage: TokenUsageOut | None = None
    conversation_id: str | None = None
    message_id: str | None = None
    tool_calls: list[ToolCallOut] = Field(default_factory=list)


class MessageOut(BaseModel):
    """A single message in a conversation."""

    id: str
    role: str
    content: str
    citations: list[SourceMetadataOut] = Field(default_factory=list)
    sources: list[SourceMetadataOut] = Field(default_factory=list)
    usage: TokenUsageOut | None = None
    prompt_version: str | None = None
    refused: bool = False
    model_id: str | None = None
    created_at: str


class ConversationOut(BaseModel):
    """A conversation with its messages."""

    id: str
    workspace_id: str
    title: str | None = None
    messages: list[MessageOut] = Field(default_factory=list)
    created_at: str
    updated_at: str


class ConversationListOut(BaseModel):
    """Paginated conversation list."""

    conversations: list[ConversationOut]
    total: int
    limit: int
    offset: int


class StreamChunkOut(BaseModel):
    """SSE event payload for streaming responses."""

    delta: str = ""
    done: bool = False
    citations: list[SourceMetadataOut] = Field(default_factory=list)
    usage: TokenUsageOut | None = None
    refused: bool = False
    refusal_reason: str | None = None
    conversation_id: str | None = None
    message_id: str | None = None
