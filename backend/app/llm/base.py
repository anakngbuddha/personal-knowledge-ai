"""LLM provider interface.

Phase 3 deliverable. The RAG layer never imports a vendor SDK; everything goes
through this ABC. The same interface supports both synchronous and streaming
generation, so the API layer can offer SSE streaming without a second code path.

Every answer carries structured citations with provenance (freshness, approval
state, vendor) so the frontend can render them inline, and every answer records
its prompt version so the regression suite can detect regressions when a
prompt changes.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Iterator
from dataclasses import dataclass, field

from app.tools.schema import ToolCall, ToolDefinition, ToolResult


@dataclass(frozen=True)
class SourceMetadata:
    """One source chunk fed to the model, with its provenance."""

    chunk_id: str
    document_id: str
    document_title: str | None
    citation: str  # human-readable citation label
    page_number: int | None = None
    slide_number: int | None = None
    sheet_name: str | None = None
    cell_range: str | None = None
    heading_path: list[str] = field(default_factory=list)
    vendor: str | None = None
    ownership: str | None = None
    approval_state: str | None = None
    sensitivity: str | None = None
    valid_until: str | None = None
    is_stale: bool = False
    source_url: str | None = None
    origin: str | None = None

    def as_dict(self) -> dict:
        return {
            "chunk_id": self.chunk_id,
            "document_id": self.document_id,
            "document_title": self.document_title,
            "citation": self.citation,
            "page_number": self.page_number,
            "slide_number": self.slide_number,
            "sheet_name": self.sheet_name,
            "cell_range": self.cell_range,
            "heading_path": list(self.heading_path),
            "vendor": self.vendor,
            "ownership": self.ownership,
            "approval_state": self.approval_state,
            "sensitivity": self.sensitivity,
            "valid_until": self.valid_until,
            "is_stale": self.is_stale,
            "source_url": self.source_url,
            "origin": self.origin,
        }


@dataclass(frozen=True)
class TokenUsage:
    """Token counts returned by the provider for budget tracking."""

    prompt_tokens: int
    completion_tokens: int
    total_tokens: int

    def as_dict(self) -> dict:
        return {
            "prompt_tokens": self.prompt_tokens,
            "completion_tokens": self.completion_tokens,
            "total_tokens": self.total_tokens,
        }


@dataclass
class GroundedAnswer:
    """A fully grounded answer with structured citations and provenance."""

    text: str
    citations: list[SourceMetadata]
    model_id: str
    prompt_version: str
    refused: bool = False
    refusal_reason: str | None = None
    usage: TokenUsage | None = None
    conversation_id: str | None = None
    message_id: str | None = None
    tool_calls: list[ToolCall] = field(default_factory=list)
    tool_results: list[ToolResult] = field(default_factory=list)
    web_note: str | None = None
    web_sources: list[SourceMetadata] = field(default_factory=list)

    def as_dict(self) -> dict:
        return {
            "text": self.text,
            "citations": [c.as_dict() for c in self.citations],
            "model_id": self.model_id,
            "prompt_version": self.prompt_version,
            "refused": self.refused,
            "refusal_reason": self.refusal_reason,
            "usage": self.usage.as_dict() if self.usage else None,
            "conversation_id": self.conversation_id,
            "message_id": self.message_id,
            "tool_calls": [c.as_dict() for c in self.tool_calls],
            "tool_results": [r.as_dict() for r in self.tool_results],
            "web_note": self.web_note,
            "web_sources": [s.as_dict() for s in self.web_sources],
        }


@dataclass
class GroundedAnswerChunk:
    """One piece of a streaming response."""

    delta: str  # incremental text
    done: bool = False
    # Populated only on the final chunk:
    citations: list[SourceMetadata] = field(default_factory=list)
    usage: TokenUsage | None = None
    refused: bool = False
    refusal_reason: str | None = None
    conversation_id: str | None = None
    message_id: str | None = None
    status: str | None = None
    web_note: str | None = None
    web_sources: list[SourceMetadata] = field(default_factory=list)


class LLMProvider(ABC):
    """Phase 3 provider interface. No vendor SDK leaks past this boundary."""

    @property
    @abstractmethod
    def model_id(self) -> str: ...

    @abstractmethod
    def generate_grounded_answer(
        self,
        question: str,
        context_chunks: list[dict],
        *,
        system_prompt: str,
        history: list[dict] | None = None,
        tools: list[ToolDefinition] | None = None,
        prior_tool_calls: list[ToolCall] | None = None,
        tool_results: list[ToolResult] | None = None,
    ) -> GroundedAnswer: ...

    @abstractmethod
    def stream_grounded_answer(
        self,
        question: str,
        context_chunks: list[dict],
        *,
        system_prompt: str,
        history: list[dict] | None = None,
        tools: list[ToolDefinition] | None = None,
        prior_tool_calls: list[ToolCall] | None = None,
        tool_results: list[ToolResult] | None = None,
    ) -> Iterator[GroundedAnswerChunk]: ...
