"""Unit tests for Web Search fallback and live search tools."""

from __future__ import annotations

from unittest.mock import MagicMock

import httpx
import pytest

from app.generation.service import PreparedContext, _attach_web
from app.retrieval.web import (
    WebFallback,
    WebPassage,
    gather_web_fallback,
    search_web,
    tavily_search,
)
from app.tools.registry import _TOOLS, ToolContext, execute_tool
from app.tools.schema import ToolCall


def test_search_web_uses_tavily(monkeypatch):
    from app.core.config import settings

    monkeypatch.setattr(settings, "tavily_api_key", "test-key")
    monkeypatch.setattr("app.retrieval.web.tavily_search", lambda *_a, **_kw: [{"title": "Hit", "url": "https://example.com", "description": "Snippet"}])

    hits = search_web("test query")
    assert len(hits) == 1
    assert hits[0]["title"] == "Hit"


def test_tavily_search_returns_attributed_results(monkeypatch):
    from app.core.config import settings
    monkeypatch.setattr(settings, "tavily_api_key", "test-key")
    client = MagicMock()
    client.post.return_value.json.return_value = {"results": [
        {"title": "Example Docs", "url": "https://example.com/docs", "content": "Architecture notes"}
    ]}
    results = tavily_search("architecture", client=client, max_results=3)
    assert results == [{"title": "Example Docs", "url": "https://example.com/docs", "description": "Architecture notes"}]
    assert client.post.call_args.kwargs["json"]["search_depth"] == "basic"


@pytest.mark.parametrize("error, expected", [
    (httpx.ConnectTimeout("timeout"), "timed out"),
    (httpx.HTTPStatusError("quota", request=httpx.Request("POST", "https://api.tavily.com/search"), response=httpx.Response(429)), "quota"),
])
def test_search_failure_is_not_reported_as_no_results(error, expected):
    def fail(_query):
        raise error
    result = gather_web_fallback("test", search_fn=fail)
    assert result.searched is False
    assert expected in result.note


def test_gather_web_fallback_extracts_passages(monkeypatch):
    def _mock_search(query):
        return [{"title": "Hit 1", "url": "https://example.com/p1", "description": "Useful passage from web snippet"}]

    class _Page:
        def __init__(self):
            self.data = b"<html><body><p>Useful passage from web page</p></body></html>"
            self.final_url = "https://example.com/p1"
            self.content_type = "text/html"

    fallback = gather_web_fallback(
        "test query",
        search_fn=_mock_search,
        fetch_fn=lambda _url: _Page(),
        robots_fn=lambda _url: None,
    )
    assert fallback.searched is True
    assert len(fallback.passages) == 1
    assert fallback.passages[0].title == "Hit 1"
    assert "Useful passage" in fallback.passages[0].text


def test_tool_web_search_registered():
    assert "tool_web_search" in _TOOLS
    tool = _TOOLS["tool_web_search"]
    assert "Search the live web" in tool.description


def test_tool_web_search_execution(monkeypatch):
    def _mock_gather(query):
        return WebFallback(
            passages=[WebPassage(title="FastAPI Web", url="https://fastapi.tiangolo.com", text="FastAPI is modern.")],
            note=None,
            searched=True,
        )

    monkeypatch.setattr("app.retrieval.web.gather_web_fallback", _mock_gather)

    ctx = MagicMock(spec=ToolContext)
    call = ToolCall(id="call_web_1", name="tool_web_search", arguments={"query": "fastapi", "max_results": 2})
    result = execute_tool(call, ctx)
    assert result.error is None
    assert result.content is not None
    assert result.content["results_count"] == 1
    assert result.content["passages"][0]["title"] == "FastAPI Web"


def test_attach_web_respects_web_search_flag(monkeypatch):
    def _mock_gather(query):
        return WebFallback(
            passages=[WebPassage(title="Web Res", url="https://test.com", text="Web content")],
            note="Web note",
            searched=True,
        )

    monkeypatch.setattr("app.generation.service.gather_web_fallback", _mock_gather)

    # 1. needs_web is False and web_search is None -> does not search
    prep1 = PreparedContext(chunks=[], sources=[], relationships_block="", needs_web=False, search_query="q")
    out1 = _attach_web(prep1, web_search=None)
    assert len(out1.chunks) == 0

    # 2. web_search is True -> forces search even if needs_web is False
    prep2 = PreparedContext(chunks=[], sources=[], relationships_block="", needs_web=False, search_query="q")
    out2 = _attach_web(prep2, web_search=True)
    assert len(out2.chunks) == 1
    assert out2.chunks[0]["metadata"]["origin"] == "web"

    # 3. web_search is False -> disables search even if needs_web is True
    prep3 = PreparedContext(chunks=[], sources=[], relationships_block="", needs_web=True, search_query="q")
    out3 = _attach_web(prep3, web_search=False)
    assert len(out3.chunks) == 0
