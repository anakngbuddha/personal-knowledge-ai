"""Fake LLM provider for testing.

Produces deterministic, canned responses that include citations referencing
whatever context chunks are provided. Used in all unit tests so they run
without a Gemini API key and without network access.

When tools are offered and the question matches a small keyword table, the
first call returns a tool request; after ToolResults are fed back it emits a
deterministic cited sentence that mentions the tool payload.
"""

from __future__ import annotations

import json
import re
from collections.abc import Iterator

from app.llm.base import (
    GroundedAnswer,
    GroundedAnswerChunk,
    LLMProvider,
    SourceMetadata,
    TokenUsage,
)
from app.llm.prompts import PROMPT_VERSION
from app.tools.schema import ToolCall, ToolDefinition, ToolResult

_TOOL_KEYWORDS = ("prerequisite", "conflict", "deploy", "requires")
_MCP_KEYWORDS = ("search the web", "brave", "vendor docs", "playwright")


class FakeLLMProvider(LLMProvider):
    """Deterministic LLM that always cites the first source and never refuses."""

    @property
    def model_id(self) -> str:
        return "fake-llm-v1"

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
    ) -> GroundedAnswer:
        if tool_results:
            return self._synthesize_from_tools(question, context_chunks, tool_results)

        if tools and _wants_tools(question):
            return GroundedAnswer(
                text="",
                citations=[],
                model_id=self.model_id,
                prompt_version=PROMPT_VERSION,
                tool_calls=_fake_tool_calls(question, tools),
                usage=TokenUsage(prompt_tokens=80, completion_tokens=10, total_tokens=90),
            )

        if not context_chunks:
            if "Answer ONLY from the provided context" in (system_prompt or ""):
                return GroundedAnswer(
                    text=(
                        "The available sources do not contain sufficient "
                        "information to answer this question. Upload a datasheet "
                        "or notes that cover this topic and ask again."
                    ),
                    citations=[],
                    model_id=self.model_id,
                    prompt_version=PROMPT_VERSION,
                    refused=True,
                    refusal_reason="insufficient_context",
                    usage=TokenUsage(prompt_tokens=100, completion_tokens=30, total_tokens=130),
                )
            return GroundedAnswer(
                text=(
                    "No matching documents were found. From general product knowledge: "
                    "I can still outline typical options at a high level. "
                    "Upload the vendor datasheet so I can cite specifics."
                ),
                citations=[],
                model_id=self.model_id,
                prompt_version=PROMPT_VERSION,
                refused=False,
                usage=TokenUsage(prompt_tokens=100, completion_tokens=40, total_tokens=140),
            )

        return self._cited_answer(question, context_chunks)

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
    ) -> Iterator[GroundedAnswerChunk]:
        answer = self.generate_grounded_answer(
            question,
            context_chunks,
            system_prompt=system_prompt,
            history=history,
            tools=tools,
            prior_tool_calls=prior_tool_calls,
            tool_results=tool_results,
        )
        words = (answer.text or "").split()
        for i, word in enumerate(words):
            delta = word if i == 0 else f" {word}"
            yield GroundedAnswerChunk(delta=delta)

        yield GroundedAnswerChunk(
            delta="",
            done=True,
            citations=answer.citations,
            usage=answer.usage,
            refused=answer.refused,
            refusal_reason=answer.refusal_reason,
        )

    def _cited_answer(self, question: str, context_chunks: list[dict]) -> GroundedAnswer:
        parts: list[str] = []
        citations: list[SourceMetadata] = []
        for chunk in context_chunks:
            idx = chunk.get("index", 0)
            meta = chunk.get("metadata", {})
            parts.append(f"Based on the documentation [source_{idx}]")
            citations.append(
                SourceMetadata(
                    chunk_id=meta.get("chunk_id", ""),
                    document_id=meta.get("document_id", ""),
                    document_title=meta.get("document_title"),
                    citation=chunk.get("citation", f"source {idx}"),
                    page_number=meta.get("page_number"),
                    slide_number=meta.get("slide_number"),
                    sheet_name=meta.get("sheet_name"),
                    cell_range=meta.get("cell_range"),
                    heading_path=meta.get("heading_path", []),
                    vendor=meta.get("vendor"),
                    ownership=meta.get("ownership"),
                    approval_state=meta.get("approval_state"),
                    sensitivity=meta.get("sensitivity"),
                    valid_until=meta.get("valid_until"),
                    is_stale=meta.get("is_stale", False),
                )
            )

        text = ", ".join(parts) + "."
        prompt_tokens = sum(len(c.get("fenced_text", "")) for c in context_chunks) + len(question)
        completion_tokens = len(text)

        return GroundedAnswer(
            text=text,
            citations=citations,
            model_id=self.model_id,
            prompt_version=PROMPT_VERSION,
            refused=False,
            usage=TokenUsage(
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
                total_tokens=prompt_tokens + completion_tokens,
            ),
        )

    def _synthesize_from_tools(
        self,
        question: str,
        context_chunks: list[dict],
        tool_results: list[ToolResult],
    ) -> GroundedAnswer:
        payload = [
            {
                "name": result.name,
                "content": result.content,
                "error": result.error,
            }
            for result in tool_results
        ]
        text = (
            "Based on catalog tools: "
            + json.dumps(payload, default=str)
            + "."
        )
        citations: list[SourceMetadata] = []
        if context_chunks:
            text += " See also [source_1]."
            cited = self._cited_answer(question, context_chunks)
            citations = cited.citations[:1]
        return GroundedAnswer(
            text=text,
            citations=citations,
            model_id=self.model_id,
            prompt_version=PROMPT_VERSION,
            usage=TokenUsage(prompt_tokens=120, completion_tokens=len(text), total_tokens=120 + len(text)),
        )


def _wants_tools(question: str) -> bool:
    lowered = question.lower()
    return any(keyword in lowered for keyword in _TOOL_KEYWORDS + _MCP_KEYWORDS)


def _extract_product(question: str) -> str:
    match = re.search(r"deploy\s+(.+?)(?:\?|$)", question, re.IGNORECASE)
    if match:
        return match.group(1).strip().rstrip("?.")
    match = re.search(r"(?:for|of)\s+([A-Z][\w][\w\s-]{1,80})", question)
    if match:
        return match.group(1).strip().rstrip("?.")
    return "unknown"


def _fake_tool_calls(question: str, tools: list[ToolDefinition]) -> list[ToolCall]:
    offered = {tool.name for tool in tools}
    product = _extract_product(question)
    lowered = question.lower()
    calls: list[ToolCall] = []
    if "conflict" in lowered and "tool_detect_contradictions" in offered:
        calls.append(
            ToolCall(
                id="call_contradictions",
                name="tool_detect_contradictions",
                arguments={"product": product} if product != "unknown" else {},
            )
        )
    if (
        any(word in lowered for word in ("prerequisite", "requires", "deploy"))
        and "tool_catalog_impact" in offered
    ):
        calls.append(
            ToolCall(
                id="call_impact",
                name="tool_catalog_impact",
                arguments={"product": product},
            )
        )
    if not calls and any(keyword in lowered for keyword in _MCP_KEYWORDS):
        for candidate in ("mcp_brave_web_search", "mcp_playwright_browser_navigate"):
            if candidate in offered:
                args = {"query": question[:500]} if "brave" in candidate else {"url": "https://example.com"}
                calls.append(ToolCall(id=f"call_{candidate}", name=candidate, arguments=args))
                break
    if not calls and "tool_hybrid_search" in offered:
        calls.append(
            ToolCall(
                id="call_search",
                name="tool_hybrid_search",
                arguments={"query": question[:500]},
            )
        )
    return calls[:4]
