"""OpenRouter chat provider.

OpenAI-compatible chat completions. Used as the text fallback (Qwen) when
Gemini is rate-limited or unreachable, and as the sole provider when
LLM_PROVIDER=openrouter.
"""

from __future__ import annotations

import json
from collections.abc import Iterator

import httpx

from app.core.config import settings
from app.core.errors import ProviderError, ProviderRateLimited
from app.core.logging import get_logger
from app.llm.base import GroundedAnswer, GroundedAnswerChunk, LLMProvider, TokenUsage
from app.llm.gemini import _detect_refusal, _extract_cited_indices, _map_citations
from app.llm.prompts import PROMPT_VERSION
from app.tools.schema import ToolCall, ToolDefinition, ToolResult

logger = get_logger(__name__)


class OpenRouterLLMProvider(LLMProvider):
    def __init__(
        self,
        api_key: str | None = None,
        model: str | None = None,
        timeout: float = 120.0,
    ) -> None:
        self._api_key = api_key if api_key is not None else settings.openrouter_api_key
        self._model = model or settings.openrouter_llm_model
        self._timeout = timeout

    @property
    def model_id(self) -> str:
        return self._model

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
        self._require_key()
        payload = self._build_payload(
            question,
            system_prompt,
            history,
            tools=tools,
            prior_tool_calls=prior_tool_calls,
            tool_results=tool_results,
        )
        response = httpx.post(
            self._url("/chat/completions"),
            headers=self._headers(),
            json=payload,
            timeout=self._timeout,
        )
        self._raise_for_status(response.status_code, response.text)
        return self._parse_response(response.json(), context_chunks)

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
        self._require_key()
        payload = self._build_payload(
            question,
            system_prompt,
            history,
            tools=tools,
            prior_tool_calls=prior_tool_calls,
            tool_results=tool_results,
            stream=True,
        )
        accumulated = ""
        usage: TokenUsage | None = None
        with httpx.stream(
            "POST",
            self._url("/chat/completions"),
            headers=self._headers(),
            json=payload,
            timeout=self._timeout,
        ) as response:
            if response.status_code != 200:
                body = response.read().decode("utf-8", errors="replace")
                self._raise_for_status(response.status_code, body)
            for line in response.iter_lines():
                if not line or not line.startswith("data: "):
                    continue
                raw = line[6:].strip()
                if raw == "[DONE]":
                    break
                try:
                    chunk = json.loads(raw)
                except json.JSONDecodeError:
                    continue
                delta = _delta_text(chunk)
                if delta:
                    accumulated += delta
                    yield GroundedAnswerChunk(delta=delta)
                chunk_usage = _usage(chunk)
                if chunk_usage:
                    usage = chunk_usage

        refused, refusal_reason = _detect_refusal(accumulated)
        citations = _map_citations(_extract_cited_indices(accumulated), context_chunks)
        yield GroundedAnswerChunk(
            delta="",
            done=True,
            citations=citations,
            usage=usage,
            refused=refused,
            refusal_reason=refusal_reason,
        )

    def _require_key(self) -> None:
        if not self._api_key:
            raise ProviderError("OPENROUTER_API_KEY is not set")

    def _url(self, path: str) -> str:
        return f"{settings.openrouter_api_base.rstrip('/')}{path}"

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }

    def _build_payload(
        self,
        question: str,
        system_prompt: str,
        history: list[dict] | None,
        *,
        tools: list[ToolDefinition] | None,
        prior_tool_calls: list[ToolCall] | None,
        tool_results: list[ToolResult] | None,
        stream: bool = False,
    ) -> dict:
        messages: list[dict] = [{"role": "system", "content": system_prompt}]
        for turn in history or []:
            role = turn.get("role")
            if role == "model":
                role = "assistant"
            if role not in ("user", "assistant", "system"):
                role = "user"
            messages.append({"role": role, "content": turn.get("content") or ""})
        messages.append({"role": "user", "content": question})
        if prior_tool_calls:
            messages.append(
                {
                    "role": "assistant",
                    "content": None,
                    "tool_calls": [
                        {
                            "id": call.id,
                            "type": "function",
                            "function": {
                                "name": call.name,
                                "arguments": json.dumps(call.arguments),
                            },
                        }
                        for call in prior_tool_calls
                    ],
                }
            )
        for result in tool_results or []:
            body = result.content if not result.error else {"error": result.error}
            messages.append(
                {
                    "role": "tool",
                    "tool_call_id": result.id,
                    "content": json.dumps(body),
                }
            )
        payload: dict = {
            "model": self._model,
            "messages": messages,
            "temperature": 0.1,
            "max_tokens": settings.generation_max_output_tokens,
        }
        if stream:
            payload["stream"] = True
        if tools:
            payload["tools"] = [
                {
                    "type": "function",
                    "function": {
                        "name": tool.name,
                        "description": tool.description,
                        "parameters": tool.parameters or {"type": "object", "properties": {}},
                    },
                }
                for tool in tools
            ]
        return payload

    def _raise_for_status(self, status_code: int, body: str) -> None:
        if status_code == 429 or status_code >= 500:
            logger.warning("OpenRouter generation error %s", status_code)
            raise ProviderRateLimited(f"OpenRouter generation error {status_code}")
        if status_code >= 400:
            raise ProviderError(f"OpenRouter generation error {status_code}: {body[:400]}")

    def _parse_response(self, data: dict, context_chunks: list[dict]) -> GroundedAnswer:
        choices = data.get("choices") or []
        if not choices:
            return GroundedAnswer(
                text="The model returned no response.",
                citations=[],
                model_id=self._model,
                prompt_version=PROMPT_VERSION,
                refused=True,
                refusal_reason="empty_response",
            )
        message = choices[0].get("message") or {}
        text = message.get("content") or ""
        usage = _usage(data)
        tool_calls = _tool_calls(message.get("tool_calls") or [])
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
            return GroundedAnswer(
                text="The model returned no response.",
                citations=[],
                model_id=self._model,
                prompt_version=PROMPT_VERSION,
                refused=True,
                refusal_reason="empty_response",
                usage=usage,
            )
        refused, refusal_reason = _detect_refusal(text)
        citations = _map_citations(_extract_cited_indices(text), context_chunks)
        return GroundedAnswer(
            text=text,
            citations=citations,
            model_id=self._model,
            prompt_version=PROMPT_VERSION,
            refused=refused,
            refusal_reason=refusal_reason,
            usage=usage,
        )


def _usage(data: dict) -> TokenUsage | None:
    usage = data.get("usage")
    if not usage:
        return None
    prompt = int(usage.get("prompt_tokens") or 0)
    completion = int(usage.get("completion_tokens") or 0)
    return TokenUsage(
        prompt_tokens=prompt,
        completion_tokens=completion,
        total_tokens=int(usage.get("total_tokens") or prompt + completion),
    )


def _delta_text(chunk: dict) -> str:
    choices = chunk.get("choices") or []
    if not choices:
        return ""
    delta = choices[0].get("delta") or {}
    content = delta.get("content")
    return content if isinstance(content, str) else ""


def _tool_calls(raw_calls: list[dict]) -> list[ToolCall]:
    calls: list[ToolCall] = []
    for index, raw in enumerate(raw_calls):
        function = raw.get("function") or {}
        name = str(function.get("name") or "")
        if not name:
            continue
        arguments = function.get("arguments") or {}
        if isinstance(arguments, str):
            try:
                arguments = json.loads(arguments) if arguments else {}
            except json.JSONDecodeError:
                arguments = {}
        if not isinstance(arguments, dict):
            arguments = {}
        calls.append(
            ToolCall(
                id=str(raw.get("id") or f"call_{index + 1}"),
                name=name,
                arguments=arguments,
            )
        )
    return calls
