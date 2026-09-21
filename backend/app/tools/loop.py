"""Bounded tool execution loop.

Native catalog tools keep a single tool round by default. When MCP tools are
offered, additional rounds are allowed so Playwright can navigate then snapshot.
A wall-clock budget still applies. The last turn always synthesizes with tools=None.
"""

from __future__ import annotations

import time
from collections.abc import Callable

from app.core.config import settings
from app.core.logging import get_logger
from app.llm.base import GroundedAnswer, LLMProvider, TokenUsage
from app.tools.schema import ToolCall, ToolDefinition, ToolResult

logger = get_logger(__name__)

ExecuteFn = Callable[[ToolCall], ToolResult]


def _has_mcp(tools: list[ToolDefinition]) -> bool:
    return any(tool.name.startswith("mcp_") for tool in tools)


def _merge_usage(first: TokenUsage | None, second: TokenUsage | None) -> TokenUsage | None:
    if first and second:
        return TokenUsage(
            prompt_tokens=first.prompt_tokens + second.prompt_tokens,
            completion_tokens=first.completion_tokens + second.completion_tokens,
            total_tokens=(
                first.prompt_tokens
                + second.prompt_tokens
                + first.completion_tokens
                + second.completion_tokens
            ),
        )
    return second or first


def run_tool_loop(
    provider: LLMProvider,
    question: str,
    context_chunks: list[dict],
    *,
    system_prompt: str,
    history: list[dict] | None,
    tools: list[ToolDefinition],
    execute: ExecuteFn,
    max_rounds: int | None = None,
    max_calls: int | None = None,
) -> GroundedAnswer:
    """Run a bounded number of tool rounds, then a synthesis turn without tools."""
    native_rounds = max_rounds if max_rounds is not None else settings.tool_max_rounds
    if _has_mcp(tools):
        rounds = max(int(native_rounds), int(settings.mcp_tool_max_rounds))
        deadline = time.monotonic() + float(settings.mcp_call_timeout_seconds)
    else:
        rounds = max(1, int(native_rounds))
        deadline = None
    max_calls = max_calls if max_calls is not None else settings.tool_max_calls_per_round

    all_calls: list[ToolCall] = []
    all_results: list[ToolResult] = []
    usage: TokenUsage | None = None
    prior_calls: list[ToolCall] | None = None
    prior_results: list[ToolResult] | None = None

    for round_index in range(max(1, rounds)):
        if deadline is not None and time.monotonic() > deadline:
            logger.warning("tool_loop hit MCP wall-clock budget after %d round(s)", round_index)
            break
        answer = provider.generate_grounded_answer(
            question,
            context_chunks,
            system_prompt=system_prompt,
            history=history,
            tools=tools,
            prior_tool_calls=prior_calls,
            tool_results=prior_results,
        )
        usage = _merge_usage(usage, answer.usage)
        if not answer.tool_calls:
            answer.tool_calls = all_calls
            answer.tool_results = all_results
            if usage:
                answer.usage = usage
            return answer

        calls = answer.tool_calls[: max(0, max_calls)]
        results: list[ToolResult] = []
        for call in calls:
            results.append(execute(call))
        logger.info(
            "tool_loop round %d executed %d call(s): %s",
            round_index + 1,
            len(results),
            [r.name for r in results],
        )
        all_calls.extend(calls)
        all_results.extend(results)
        prior_calls = calls
        prior_results = results

    synthesis = provider.generate_grounded_answer(
        question,
        context_chunks,
        system_prompt=system_prompt,
        history=history,
        tools=None,
        prior_tool_calls=all_calls or prior_calls,
        tool_results=all_results or prior_results,
    )
    synthesis.tool_calls = all_calls
    synthesis.tool_results = all_results
    combined = _merge_usage(usage, synthesis.usage)
    if combined:
        synthesis.usage = combined
    return synthesis
