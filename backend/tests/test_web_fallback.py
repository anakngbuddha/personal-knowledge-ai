"""Web fallback runs only when local passages do not cover the question."""

from app.core.config import settings
from app.core.errors import SsrfBlocked
from app.documents.injection import UNTRUSTED_OPEN
from app.generation.service import PreparedContext, _attach_web, hits_are_weak
from app.llm.base import GroundedAnswerChunk
from app.retrieval.web import gather_web_fallback
import uuid

from app.security.principal import owner_principal


class _Hit:
    def __init__(self, text: str):
        self.text = text


class _Page:
    def __init__(self, data: bytes, url: str = "https://example.com/spec"):
        self.data = data
        self.final_url = url
        self.content_type = "text/html"


def test_strong_local_hit_is_not_weak():
    hits = [_Hit("Jabra Speak 750 pricing and compatibility notes")]
    assert hits_are_weak(hits, "Jabra Speak pricing") is False


def test_empty_local_hits_are_weak():
    assert hits_are_weak([], "anything") is True


def test_missing_brave_key_does_not_fail(monkeypatch):
    monkeypatch.setattr(settings, "brave_api_key", "")
    result = gather_web_fallback("room systems")
    assert result.passages == []
    assert result.note == "Web search is not configured."
    assert result.searched is False


def test_weak_retrieval_fetches_and_fences(monkeypatch):
    def search(_query):
        return [{"url": "https://vendor.example/bar", "title": "Video Bar", "description": "specs"}]

    def fetch(_url):
        return _Page(b"<html><body><p>The video bar needs a speaker.</p><script>alert(1)</script></body></html>")

    monkeypatch.setattr(
        "app.generation.service.gather_web_fallback",
        lambda query: gather_web_fallback(query, search_fn=search, fetch_fn=fetch, robots_fn=lambda _url: None),
    )
    prepared = PreparedContext(
        chunks=[],
        sources=[],
        relationships_block="",
        needs_web=True,
        search_query="video bar speaker",
    )
    attached = _attach_web(prepared)
    assert attached.web_sources[0].source_url == "https://example.com/spec"
    assert attached.web_sources[0].origin == "web"
    assert "video bar needs a speaker" in attached.chunks[0]["fenced_text"]
    assert "alert" not in attached.chunks[0]["fenced_text"]
    assert UNTRUSTED_OPEN.split(" id=")[0] in attached.chunks[0]["fenced_text"]


def test_ssrf_blocked_pages_are_dropped():
    def search(_query):
        return [{"url": "http://169.254.169.254/latest", "title": "meta", "description": "secret"}]

    def fetch(_url):
        raise SsrfBlocked("private address")

    result = gather_web_fallback("meta", search_fn=search, fetch_fn=fetch, robots_fn=lambda _url: None)
    assert result.passages == []
    assert result.searched is True


def test_strong_context_does_not_search_the_web(monkeypatch):
    def _boom(_query):
        raise AssertionError("web search should not run")

    monkeypatch.setattr("app.generation.service.gather_web_fallback", _boom)
    prepared = PreparedContext(
        chunks=[],
        sources=[],
        relationships_block="",
        needs_web=False,
        search_query="covered",
    )
    assert _attach_web(prepared) is prepared


def test_ask_stream_yields_delta_before_done(monkeypatch):
    from app.generation.service import ask_stream

    prepared = PreparedContext(
        chunks=[{"index": 1, "fenced_text": "notes", "citation": "Doc", "metadata": {}}],
        sources=[],
        relationships_block="",
        needs_web=False,
        search_query="pricing",
    )
    monkeypatch.setattr("app.generation.service.check_rate_limit", lambda *_a, **_k: None)
    monkeypatch.setattr("app.generation.service.check_token_budget", lambda *_a, **_k: None)
    monkeypatch.setattr("app.generation.service._prepare_context", lambda *_a, **_k: prepared)

    class _Provider:
        model_id = "fake-stream"

        def stream_grounded_answer(self, *_a, **_k):
            yield GroundedAnswerChunk(delta="Price")
            yield GroundedAnswerChunk(delta=" is listed.", done=False)
            yield GroundedAnswerChunk(delta="", done=True)

    monkeypatch.setattr("app.generation.service.get_llm_provider", lambda: _Provider())
    chunks = list(
        ask_stream(
            None,  # type: ignore[arg-type]
            principal=owner_principal(uuid.uuid4()),
            question="What is the price?",
            enable_tools=False,
        )
    )
    assert chunks[0].done is False
    assert chunks[0].delta == "Price"
    assert chunks[-1].done is True
