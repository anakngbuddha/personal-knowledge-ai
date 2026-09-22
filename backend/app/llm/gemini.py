"""Gemini LLM provider for Phase 3 grounded generation.

Uses httpx directly (same pattern as the embedding provider) rather than a
vendor SDK, giving full control over streaming, retries, and error handling.
Streams via the Gemini `streamGenerateContent` endpoint for SSE support.
"""

from __future__ import annotations

import json
import re
from collections.abc import Iterator

import httpx
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from app.core.config import settings
from app.core.errors import ProviderError, ProviderRateLimited
from app.core.logging import get_logger
from app.llm.base import (
    GroundedAnswer,
    GroundedAnswerChunk,
    LLMProvider,
    SourceMetadata,
    TokenUsage,
)
from app.llm.limiter import acquire_gemini
from app.llm.prompts import PROMPT_VERSION
from app.tools.schema import ToolCall, ToolDefinition, ToolResult

logger = get_logger(__name__)

_CITATION_PATTERN = re.compile(r"\[source_(\d+)\]")


class GeminiLLMProvider(LLMProvider):
    """Gemini generation provider behind the LLMProvider interface."""

    def __init__(
        self,
        api_key: str | None = None,
        model: str | None = None,
        timeout: float = 120.0,
    ) -> None:
        self._api_key = api_key or settings.gemini_api_key
        self._model = model or settings.gemini_generation_model
        self._timeout = timeout
        if not self._api_key:
            raise ProviderError("GEMINI_API_KEY is not set")

    @property
    def model_id(self) -> str:
        return self._model

    @retry(
        retry=retry_if_exception_type((ProviderRateLimited, httpx.TransportError)),
        wait=wait_exponential(multiplier=2, min=2, max=60),
        stop=stop_after_attempt(4),
        reraise=True,
    )
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
        url = (
            f"{settings.gemini_api_base}/models/{self._model}:generateContent"
        )
        payload = self._build_payload(
            question,
            context_chunks,
            system_prompt,
            history,
            tools=tools,
            prior_tool_calls=prior_tool_calls,
            tool_results=tool_results,
        )

        acquire_gemini()
        try:
            response = httpx.post(
                url,
                params={"key": self._api_key},
                json=payload,
                timeout=self._timeout,
            )
        except httpx.TransportError:
            raise

        self._check_status(response)
        data = response.json()
        return self._parse_response(data, context_chunks)

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
        url = (
            f"{settings.gemini_api_base}/models/{self._model}:streamGenerateContent"
        )
        payload = self._build_payload(
            question,
            context_chunks,
            system_prompt,
            history,
            tools=tools,
            prior_tool_calls=prior_tool_calls,
            tool_results=tool_results,
        )

        accumulated_text = ""
        usage: TokenUsage | None = None

        acquire_gemini()
        try:
            with httpx.stream(
                "POST",
                url,
                params={"key": self._api_key, "alt": "sse"},
                json=payload,
                timeout=self._timeout,
            ) as response:
                if response.status_code != 200:
                    body = response.read().decode("utf-8", errors="replace")
                    self._raise_for_status(response.status_code, body)

                for line in response.iter_lines():
                    if not line or not line.startswith("data: "):
                        continue
                    raw = line[6:]
                    if raw.strip() == "[DONE]":
                        break
                    try:
                        chunk_data = json.loads(raw)
                    except json.JSONDecodeError:
                        continue

                    delta = self._extract_delta(chunk_data)
                    if delta:
                        accumulated_text += delta
                        yield GroundedAnswerChunk(delta=delta)

                    chunk_usage = self._extract_usage(chunk_data)
                    if chunk_usage:
                        usage = chunk_usage

        except httpx.TransportError:
            raise
        except ProviderRateLimited:
            raise
        except ProviderError:
            raise

        # Final chunk with citations and usage
        refused, refusal_reason = _detect_refusal(accumulated_text)
        cited_indices = _extract_cited_indices(accumulated_text)
        citations = _map_citations(cited_indices, context_chunks)

        yield GroundedAnswerChunk(
            delta="",
            done=True,
            citations=citations,
            usage=usage,
            refused=refused,
            refusal_reason=refusal_reason,
        )

    def _build_payload(
        self,
        question: str,
        context_chunks: list[dict],
        system_prompt: str,
        history: list[dict] | None,
        tools: list[ToolDefinition] | None = None,
        prior_tool_calls: list[ToolCall] | None = None,
        tool_results: list[ToolResult] | None = None,
    ) -> dict:
        contents: list[dict] = []

        if history:
            for turn in history:
                role = "user" if turn.get("role") == "user" else "model"
                contents.append({
                    "role": role,
                    "parts": [{"text": turn["content"]}],
                })

        contents.append({
            "role": "user",
            "parts": [{"text": question}],
        })

        if prior_tool_calls:
            contents.append({
                "role": "model",
                "parts": [
                    {
                        "functionCall": {
                            "name": call.name,
                            "args": call.arguments,
                        }
                    }
                    for call in prior_tool_calls
                ],
            })
        if tool_results:
            contents.append({
                "role": "user",
                "parts": [
                    {
                        "functionResponse": {
                            "name": result.name,
                            "response": result.content if not result.error else {"error": result.error},
                        }
                    }
                    for result in tool_results
                ],
            })

        payload: dict = {
            "system_instruction": {
                "parts": [{"text": system_prompt}],
            },
            "contents": contents,
            "generationConfig": {
                "temperature": 0.1,
                "maxOutputTokens": 4096,
            },
        }
        if tools:
            payload["tools"] = [_gemini_tools(tools)]
        return payload

    def _check_status(self, response: httpx.Response) -> None:
        self._raise_for_status(response.status_code, response.text)

    def _raise_for_status(self, status_code: int, body: str) -> None:
        if status_code == 429:
            logger.warning("Gemini generation rate limited (429)")
            raise ProviderRateLimited("Gemini generation rate limit reached")
        if status_code >= 500:
            raise ProviderRateLimited(
                f"Gemini generation transient error {status_code}"
            )
        if status_code >= 400:
            raise ProviderError(
                f"Gemini generation error {status_code}: {body[:400]}"
            )

    def _parse_response(
        self, data: dict, context_chunks: list[dict]
    ) -> GroundedAnswer:
        candidates = data.get("candidates", [])
        if not candidates:
            return GroundedAnswer(
                text="The model returned no response.",
                citations=[],
                model_id=self._model,
                prompt_version=PROMPT_VERSION,
                refused=True,
                refusal_reason="empty_response",
            )

        parts = candidates[0].get("content", {}).get("parts", [])
        text = "".join(part.get("text", "") for part in parts)
        usage = self._extract_usage(data)
        tool_calls = _extract_function_calls(parts)

        if tool_calls:
            return GroundedAnswer(
                text=text,
                citations=[],
                model_id=self._model,
                prompt_version=PROMPT_VERSION,
                usage=usage,
                tool_calls=tool_calls,
            )

        if not text:
            finish_reason = candidates[0].get("finishReason")
            return GroundedAnswer(
                text="The model returned no response.",
                citations=[],
                model_id=self._model,
                prompt_version=PROMPT_VERSION,
                refused=True,
                refusal_reason=f"empty_response_{finish_reason}" if finish_reason else "empty_response",
                usage=usage,
            )

        refused, refusal_reason = _detect_refusal(text)
        cited_indices = _extract_cited_indices(text)
        citations = _map_citations(cited_indices, context_chunks)

        return GroundedAnswer(
            text=text,
            citations=citations,
            model_id=self._model,
            prompt_version=PROMPT_VERSION,
            refused=refused,
            refusal_reason=refusal_reason,
            usage=usage,
        )

    @staticmethod
    def _extract_delta(chunk_data: dict) -> str:
        candidates = chunk_data.get("candidates", [])
        if not candidates:
            return ""
        parts = candidates[0].get("content", {}).get("parts", [])
        return "".join(part.get("text", "") for part in parts)

    @staticmethod
    def _extract_usage(data: dict) -> TokenUsage | None:
        usage = data.get("usageMetadata")
        if not usage:
            return None
        prompt = usage.get("promptTokenCount", 0)
        completion = usage.get("candidatesTokenCount", 0)
        return TokenUsage(
            prompt_tokens=prompt,
            completion_tokens=completion,
            total_tokens=prompt + completion,
        )


def _gemini_tools(tools: list[ToolDefinition]) -> dict:
    return {
        "functionDeclarations": [
            {
                "name": tool.name,
                "description": tool.description,
                "parameters": _json_schema_to_gemini(tool.parameters),
            }
            for tool in tools
        ]
    }


_GEMINI_TYPES = {
    "object": "OBJECT",
    "string": "STRING",
    "number": "NUMBER",
    "integer": "INTEGER",
    "boolean": "BOOLEAN",
    "array": "ARRAY",
}


def _json_schema_to_gemini(schema: dict) -> dict:
    """Convert a JSON Schema fragment into Gemini's uppercase type names."""
    if not schema:
        return {"type": "OBJECT", "properties": {}}
    out: dict = {}
    raw_type = schema.get("type")
    if raw_type:
        out["type"] = _GEMINI_TYPES.get(str(raw_type).lower(), "OBJECT")
    if "properties" in schema:
        out["properties"] = {
            key: _json_schema_to_gemini(value)
            for key, value in schema["properties"].items()
        }
    if "required" in schema:
        out["required"] = list(schema["required"])
    if "description" in schema:
        out["description"] = schema["description"]
    if "items" in schema and isinstance(schema["items"], dict):
        out["items"] = _json_schema_to_gemini(schema["items"])
    if schema.get("anyOf") or schema.get("oneOf"):
        # Optional Pydantic fields become anyOf [type, null]; pick the first non-null.
        variants = schema.get("anyOf") or schema.get("oneOf") or []
        non_null = [v for v in variants if v.get("type") != "null"]
        if non_null:
            return _json_schema_to_gemini(non_null[0])
    return out or {"type": "OBJECT", "properties": {}}


def _extract_function_calls(parts: list[dict]) -> list[ToolCall]:
    calls: list[ToolCall] = []
    for part in parts:
        raw = part.get("functionCall")
        if not raw:
            continue
        name = str(raw.get("name") or "")
        if not name:
            continue
        args = raw.get("args") or raw.get("arguments") or {}
        if not isinstance(args, dict):
            args = {}
        calls.append(
            ToolCall(
                id=f"call_{len(calls) + 1}",
                name=name,
                arguments=args,
            )
        )
    return calls


def _detect_refusal(text: str) -> tuple[bool, str | None]:
    """Detect whether the model refused to answer due to insufficient context."""
    refusal_phrases = [
        "do not contain sufficient information",
        "does not contain sufficient information",
        "do not contain enough information",
        "does not contain enough information",
        "cannot answer this question",
        "unable to answer",
        "no relevant information",
        "not covered in the available sources",
        "not mentioned in the provided sources",
        "not found in the provided sources",
        "no information available",
    ]
    text_lower = text.lower()
    for phrase in refusal_phrases:
        if phrase in text_lower:
            return True, "insufficient_context"
    return False, None


def _extract_cited_indices(text: str) -> list[int]:
    """Extract unique source indices cited in the answer text."""
    matches = _CITATION_PATTERN.findall(text)
    seen: set[int] = set()
    result: list[int] = []
    for m in matches:
        idx = int(m)
        if idx not in seen:
            seen.add(idx)
            result.append(idx)
    return result


def _map_citations(
    cited_indices: list[int], context_chunks: list[dict]
) -> list[SourceMetadata]:
    """Map cited source indices back to SourceMetadata from context_chunks."""
    citations: list[SourceMetadata] = []
    for idx in cited_indices:
        # Find the matching chunk by index
        chunk = None
        for c in context_chunks:
            if c.get("index") == idx:
                chunk = c
                break
        if chunk is None:
            continue

        meta = chunk.get("metadata", {})
        citations.append(
            SourceMetadata(
                chunk_id=meta.get("chunk_id", ""),
                document_id=meta.get("document_id", ""),
                document_title=meta.get("document_title"),
                citation=chunk.get("citation", ""),
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
    return citations
