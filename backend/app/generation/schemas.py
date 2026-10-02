"""Pydantic schemas for the Phase 3 generation API.

All request/response models for the /ask and /conversations endpoints.
Every answer carries structured citations with provenance metadata so the
frontend can render freshness, approval state, and vendor inline.
"""

from __future__ import annotations

import uuid
from typing import Literal

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
    source_url: str | None = None
    origin: str | None = None
    # Claim-level support (lexical overlap between the citing claim and the passage).
    support_score: float | None = None
    weakly_supported: bool | None = None


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
    notebook_id: str | None = None
    attachment_document_ids: list[uuid.UUID] = Field(default_factory=list, max_length=12)
    # Tool-enabled answers are not streamed token by token (see ask_stream).
    enable_tools: bool = False
    # Knowledge mode. True (default) = strict, sources only. False = expert: general
    # guidance allowed, but only under a separately labeled heading.
    strict_mode: bool = True
    # Web search mode: None = auto (search when documents weak), True = force web search, False = disabled
    web_search: bool | None = None
    # Optional active session goal
    goal: str | None = Field(default=None, max_length=1000)


MentionCategory = Literal["note", "website", "connector", "product"]


class MentionTargetOut(BaseModel):
    """Autocomplete target for @ mentions (notes, products, connectors, websites)."""

    id: str
    ref: str
    name: str
    category: MentionCategory
    subtitle: str | None = None
    icon: str | None = None


class ConnectionNodeOut(BaseModel):
    """Related product node in a connections lookup."""

    id: str
    name: str
    relation_type: str
    evidence: str | None = None


class ProductConnectionsOut(BaseModel):
    """Detailed connections and dependencies for a product (/connections command)."""

    product_id: str
    product_name: str
    vendor: str | None = None
    category: str | None = None
    prerequisites: list[ConnectionNodeOut] = Field(default_factory=list)
    conflicts: list[ConnectionNodeOut] = Field(default_factory=list)
    integrations: list[ConnectionNodeOut] = Field(default_factory=list)
    alternatives: list[ConnectionNodeOut] = Field(default_factory=list)
    collateral_count: int = 0


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
    web_note: str | None = None
    web_sources: list[SourceMetadataOut] = Field(default_factory=list)
    active_goal: str | None = None
    connections_result: ProductConnectionsOut | None = None


class WebSourceSaveIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    url: str = Field(min_length=8, max_length=2000)
    title: str | None = Field(default=None, max_length=300)
    notebook_id: str | None = None


class WebSourceSaveOut(BaseModel):
    document_id: str
    notebook_id: str | None = None


class MessageOut(BaseModel):
    """A single message in a conversation."""

    id: str
    role: str
    content: str
    citations: list[SourceMetadataOut] = Field(default_factory=list)
    sources: list[SourceMetadataOut] = Field(default_factory=list)
    usage: TokenUsageOut | None = None
    tool_calls: list[ToolCallOut] = Field(default_factory=list)
    prompt_version: str | None = None
    refused: bool = False
    model_id: str | None = None
    created_at: str
    active_goal: str | None = None
    connections_result: ProductConnectionsOut | None = None


class ConversationOut(BaseModel):
    """A conversation with its messages."""

    id: str
    workspace_id: str
    notebook_id: str | None = None
    title: str | None = None
    goal: str | None = None
    messages: list[MessageOut] = Field(default_factory=list)
    message_total: int = 0
    message_limit: int = 100
    message_offset: int = 0
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
    status: str | None = None
    web_note: str | None = None
    web_sources: list[SourceMetadataOut] = Field(default_factory=list)
    active_goal: str | None = None
    connections_result: ProductConnectionsOut | None = None
