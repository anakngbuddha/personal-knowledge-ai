"""Fake LLM provider for testing.

Produces deterministic, canned responses that include citations referencing
whatever context chunks are provided. Used in all unit tests so they run
without a Gemini API key and without network access.
"""

from __future__ import annotations

from collections.abc import Iterator

from app.llm.base import (
    GroundedAnswer,
    GroundedAnswerChunk,
    LLMProvider,
    SourceMetadata,
    TokenUsage,
)
from app.llm.prompts import PROMPT_VERSION


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
    ) -> GroundedAnswer:
        if not context_chunks:
            return GroundedAnswer(
                text=(
                    "The available sources do not contain sufficient "
                    "information to answer this question."
                ),
                citations=[],
                model_id=self.model_id,
                prompt_version=PROMPT_VERSION,
                refused=True,
                refusal_reason="insufficient_context",
                usage=TokenUsage(prompt_tokens=100, completion_tokens=30, total_tokens=130),
            )

        # Build a deterministic answer citing each source
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

    def stream_grounded_answer(
        self,
        question: str,
        context_chunks: list[dict],
        *,
        system_prompt: str,
        history: list[dict] | None = None,
    ) -> Iterator[GroundedAnswerChunk]:
        answer = self.generate_grounded_answer(
            question, context_chunks, system_prompt=system_prompt, history=history
        )
        # Simulate streaming by yielding word by word
        words = answer.text.split()
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
