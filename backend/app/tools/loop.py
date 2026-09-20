"""Bounded single-turn tool execution loop.

LLM may request tools once. The backend executes the allowlisted functions and
asks the model to synthesize. A second tool request is ignored: we synthesize
from the results already collected.
"""

from __future__ import annotations

from collections.abc import Callable

from app.core.config import settings
from app.core.logging import get_logger
from app.llm.base import GroundedAnswer, LLMProvider, TokenUsage
from app.tools.schema import ToolCall, ToolDefinition, ToolResult

logger = get_logger(__name__)

ExecuteFn = Callable[[ToolCall], ToolResult]


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
    """Run at most one tool round, then a synthesis turn without further tools."""
    max_rounds = max_rounds if max_rounds is not None else settings.tool_max_rounds
    max_calls = max_calls if max_calls is not None else settings.tool_max_calls_per_round

    first = provider.generate_grounded_answer(
        question,
        context_chunks,
        system_prompt=system_prompt,
        history=history,
        tools=tools,
    )
    if not first.tool_calls:
        return first

    calls = first.tool_calls[: max(0, max_calls)]
    results: list[ToolResult] = []
    for call in calls:
        results.append(execute(call))

    logger.info(
        "tool_loop executed %d call(s): %s",
        len(results),
        [r.name for r in results],
    )

    # Hard bound: synthesis turn has tools=None so the model cannot loop.
    synthesis = provider.generate_grounded_answer(
        question,
        context_chunks,
        system_prompt=system_prompt,
        history=history,
        tools=None,
        prior_tool_calls=calls,
        tool_results=results,
    )
    synthesis.tool_calls = calls
    synthesis.tool_results = results
    if first.usage and synthesis.usage:
        combined = TokenUsage(
            prompt_tokens=first.usage.prompt_tokens + synthesis.usage.prompt_tokens,
            completion_tokens=first.usage.completion_tokens + synthesis.usage.completion_tokens,
            total_tokens=(
                first.usage.prompt_tokens
                + synthesis.usage.prompt_tokens
                + first.usage.completion_tokens
                + synthesis.usage.completion_tokens
            ),
        )
        synthesis.usage = combined
    elif first.usage and synthesis.usage is None:
        synthesis.usage = first.usage

    # max_rounds is currently 1 by design; kept as a config knob for tests.
    _ = max_rounds
    return synthesis
