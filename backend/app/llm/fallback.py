"""Try Gemini first; use OpenRouter only when Gemini is rate-limited.

OpenRouter (Qwen) is strictly a rate-limit fallback. Only ProviderRateLimited
(Gemini 429, plus 5xx which gemini.py maps to it) hands the request over.
Any other Gemini failure, such as a 400 Bad Request or a network error, is
raised as-is so real bugs are visible instead of being masked by the fallback.
An empty OPENROUTER_API_KEY leaves the original error in place.

When *both* providers return rate-limit errors, the wrapper waits with
exponential backoff (up to MAX_RETRIES attempts) before giving up.
"""

from __future__ import annotations

import time
from collections.abc import Iterator

from app.core.config import settings
from app.core.errors import ProviderRateLimited
from app.core.logging import get_logger
from app.jobs.backoff import backoff_seconds
from app.llm.base import GroundedAnswer, GroundedAnswerChunk, LLMProvider
from app.tools.schema import ToolCall, ToolDefinition, ToolResult

logger = get_logger(__name__)

# Only rate limiting on the primary triggers the OpenRouter fallback.
_FALLBACK_ERRORS = (ProviderRateLimited,)

# Retry configuration for when both providers are rate-limited.
MAX_RETRIES = 3
_BACKOFF_BASE = 2.0   # seconds
_BACKOFF_MAX = 30.0    # seconds


def _brief(exc: BaseException, limit: int = 300) -> str:
    text = str(exc) or type(exc).__name__
    return text if len(text) <= limit else text[:limit] + "..."


class FallbackLLMProvider(LLMProvider):
    def __init__(self, primary: LLMProvider, fallback: LLMProvider | None = None) -> None:
        self._primary = primary
        self._fallback = fallback

    @property
    def model_id(self) -> str:
        return self._primary.model_id

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
        last_exc: BaseException | None = None
        for attempt in range(1, MAX_RETRIES + 1):
            try:
                return self._try_generate(
                    question,
                    context_chunks,
                    system_prompt=system_prompt,
                    history=history,
                    tools=tools,
                    prior_tool_calls=prior_tool_calls,
                    tool_results=tool_results,
                )
            except ProviderRateLimited as exc:
                last_exc = exc
                if attempt < MAX_RETRIES:
                    delay = backoff_seconds(
                        attempt, base=_BACKOFF_BASE, maximum=_BACKOFF_MAX,
                    )
                    logger.warning(
                        "All LLM providers rate-limited (attempt %d/%d); "
                        "retrying in %.1fs",
                        attempt, MAX_RETRIES, delay,
                    )
                    time.sleep(delay)
        raise last_exc  # type: ignore[misc]

    def _try_generate(
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
        """Single attempt: Gemini, then OpenRouter only if Gemini is rate-limited."""
        try:
            return self._primary.generate_grounded_answer(
                question,
                context_chunks,
                system_prompt=system_prompt,
                history=history,
                tools=tools,
                prior_tool_calls=prior_tool_calls,
                tool_results=tool_results,
            )
        except _FALLBACK_ERRORS as exc:
            fallback = self._ready_fallback()
            if fallback is None:
                raise
            logger.warning(
                "Primary LLM rate-limited (%s); using OpenRouter", _brief(exc),
            )
            return fallback.generate_grounded_answer(
                question,
                context_chunks,
                system_prompt=system_prompt,
                history=history,
                tools=tools,
                prior_tool_calls=prior_tool_calls,
                tool_results=tool_results,
            )

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
        kwargs = dict(
            system_prompt=system_prompt,
            history=history,
            tools=tools,
            prior_tool_calls=prior_tool_calls,
            tool_results=tool_results,
        )
        last_exc: BaseException | None = None
        for attempt in range(1, MAX_RETRIES + 1):
            try:
                yield from self._try_stream(question, context_chunks, **kwargs)
                return
            except ProviderRateLimited as exc:
                last_exc = exc
                if attempt < MAX_RETRIES:
                    delay = backoff_seconds(
                        attempt, base=_BACKOFF_BASE, maximum=_BACKOFF_MAX,
                    )
                    logger.warning(
                        "All LLM providers rate-limited on stream (attempt %d/%d); "
                        "retrying in %.1fs",
                        attempt, MAX_RETRIES, delay,
                    )
                    time.sleep(delay)
        raise last_exc  # type: ignore[misc]

    def _try_stream(
        self,
        question: str,
        context_chunks: list[dict],
        **kwargs,
    ) -> Iterator[GroundedAnswerChunk]:
        """Single attempt: Gemini stream, then OpenRouter only if Gemini is rate-limited."""
        stream = self._primary.stream_grounded_answer(question, context_chunks, **kwargs)
        try:
            first = next(stream)
        except StopIteration:
            return
        except _FALLBACK_ERRORS as exc:
            fallback = self._ready_fallback()
            if fallback is None:
                raise
            logger.warning(
                "Primary LLM stream rate-limited (%s); using OpenRouter", _brief(exc),
            )
            yield from fallback.stream_grounded_answer(question, context_chunks, **kwargs)
            return
        yield first
        yield from stream

    def _ready_fallback(self) -> LLMProvider | None:
        if not settings.openrouter_api_key:
            return None
        if self._fallback is None:
            from app.llm.openrouter import OpenRouterLLMProvider

            self._fallback = OpenRouterLLMProvider()
        return self._fallback
