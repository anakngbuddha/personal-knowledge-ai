"""Tool-enabled answers are labelled as not streamed (audit finding 10)."""

from __future__ import annotations

import uuid

from app.generation import service
from app.llm.base import GroundedAnswer
from app.security.principal import owner_principal


def test_tool_path_does_not_fake_token_streaming(monkeypatch):
    answer = GroundedAnswer(text="one two three four", citations=[], model_id="fake", prompt_version="x")
    monkeypatch.setattr(service, "ask", lambda *a, **k: answer)
    chunks = list(
        service.ask_stream(None, principal=owner_principal(uuid.uuid4()), question="q", enable_tools=True)
    )
    assert "not streamed" in (chunks[0].status or "")
    text_chunks = [c for c in chunks if c.delta]
    assert len(text_chunks) == 1
    assert text_chunks[0].delta == "one two three four"
    assert chunks[-1].done is True
