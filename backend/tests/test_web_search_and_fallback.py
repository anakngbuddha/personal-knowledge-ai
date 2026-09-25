"""Unit tests for Web Search fallback and live search tools."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from app.generation.service import PreparedContext, _attach_web
from app.retrieval.web import (
    WebFallback,
    WebPassage,
    duckduckgo_search,
    gather_web_fallback,
    search_web,
)
from app.tools.registry import _TOOLS, ToolContext, execute_tool
from app.tools.schema import ToolCall


def test_duckduckgo_search_returns_parsed_results(monkeypatch):
    sample_html = """
    <html><body>
      <div class="result">
        <a class="result__title" href="https://duckduckgo.com/l/?uddg=https%3A%2F%2Fexample.com%2Fdocs">Example Docs</a>
        <a class="result__snippet">Documentation on software architecture.</a>
      </div>
    </body></html>
    """
    mock_resp = MagicMock()
    mock_resp.text = sample_html
    mock_resp.raise_for_status = MagicMock()

    mock_client = MagicMock()
    mock_client.post.return_value = mock_resp

    results = duckduckgo_search("architecture", client=mock_client, max_results=5)
    assert len(results) == 1
    assert results[0]["title"] == "Example Docs"
    assert results[0]["url"] == "https://example.com/docs"
    assert "Documentation" in results[0]["description"]


def test_search_web_falls_back_to_duckduckgo(monkeypatch):
    from app.core.config import settings

    monkeypatch.setattr(settings, "brave_api_key", None)

    def _mock_ddg(query, client=None, max_results=None):
        return [{"title": "DDG Hit", "url": "https://ddg.example.com", "description": "Snippet"}]

    monkeypatch.setattr("app.retrieval.web.duckduckgo_search", _mock_ddg)

    hits = search_web("test query")
    assert len(hits) == 1
    assert hits[0]["title"] == "DDG Hit"


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
