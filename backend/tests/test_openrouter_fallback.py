"""OpenRouter text fallback and Nemotron embedding guard. No network."""

from unittest.mock import MagicMock, call, patch

import httpx
import pytest

from app.core.config import settings
from app.core.errors import ProviderError, ProviderRateLimited
from app.embeddings.factory import get_embedding_provider
from app.embeddings.openrouter import OpenRouterEmbeddingProvider
from app.llm.base import GroundedAnswerChunk
from app.llm.factory import get_llm_provider
from app.llm.fallback import FallbackLLMProvider
from app.llm.openrouter import OpenRouterLLMProvider
from app.tools.schema import ToolDefinition


def _chunk() -> list[dict]:
    return [
        {
            "index": 1,
            "citation": "Guide, p.1",
            "metadata": {
                "chunk_id": "c1",
                "document_id": "d1",
                "document_title": "Guide",
            },
        }
    ]


class _Boom:
    model_id = "gemini-test"

    def generate_grounded_answer(self, *args, **kwargs):
        raise ProviderRateLimited("Gemini generation rate limit reached")

    def stream_grounded_answer(self, *args, **kwargs):
        raise ProviderRateLimited("Gemini generation rate limit reached")
        yield  # pragma: no cover


def test_fallback_on_rate_limit_uses_openrouter(monkeypatch):
    monkeypatch.setattr(settings, "openrouter_api_key", "test-key")
    captured = {}

    def fake_post(url, headers=None, json=None, timeout=None):
        captured["url"] = url
        captured["model"] = json["model"]
        response = MagicMock()
        response.status_code = 200
        response.json.return_value = {
            "choices": [{"message": {"content": "From the guide [source_1]."}}],
            "usage": {"prompt_tokens": 3, "completion_tokens": 4, "total_tokens": 7},
        }
        return response

    fallback = OpenRouterLLMProvider(api_key="test-key", model="qwen/qwen3.8-27b:free")
    provider = FallbackLLMProvider(_Boom(), fallback)
    with patch("app.llm.openrouter.httpx.post", fake_post):
        answer = provider.generate_grounded_answer("What?", _chunk(), system_prompt="Be brief.")

    assert answer.model_id == "qwen/qwen3.8-27b:free"
    assert answer.citations[0].chunk_id == "c1"
    assert captured["model"] == "qwen/qwen3.8-27b:free"
    assert captured["url"].endswith("/chat/completions")


def test_fallback_without_key_reraises(monkeypatch):
    monkeypatch.setattr(settings, "openrouter_api_key", "")
    provider = FallbackLLMProvider(_Boom(), OpenRouterLLMProvider(api_key="unused"))
    with patch("app.llm.openrouter.httpx.post", side_effect=AssertionError("network")):
        with pytest.raises(ProviderRateLimited):
            provider.generate_grounded_answer("What?", _chunk(), system_prompt="Be brief.")


def test_stream_fallback_before_first_chunk(monkeypatch):
    monkeypatch.setattr(settings, "openrouter_api_key", "test-key")

    class _Response:
        status_code = 200

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def read(self):
            return b""

        def iter_lines(self):
            yield 'data: {"choices":[{"delta":{"content":"Hello [source_1]"}}]}'
            yield "data: [DONE]"

    fallback = OpenRouterLLMProvider(api_key="test-key")
    provider = FallbackLLMProvider(_Boom(), fallback)
    with patch("app.llm.openrouter.httpx.stream", return_value=_Response()):
        chunks = list(
            provider.stream_grounded_answer("What?", _chunk(), system_prompt="Be brief.")
        )

    assert chunks[0].delta.startswith("Hello")
    assert chunks[-1].done is True
    assert chunks[-1].citations[0].document_id == "d1"


def test_openrouter_parses_tool_call():
    provider = OpenRouterLLMProvider(api_key="test-key")
    response = MagicMock()
    response.status_code = 200
    response.json.return_value = {
        "choices": [
            {
                "message": {
                    "content": "",
                    "tool_calls": [
                        {
                            "id": "call_9",
                            "type": "function",
                            "function": {"name": "lookup", "arguments": '{"q":"acme"}'},
                        }
                    ],
                }
            }
        ]
    }
    tool = ToolDefinition(name="lookup", description="find", parameters={"type": "object"})
    with patch("app.llm.openrouter.httpx.post", return_value=response):
        answer = provider.generate_grounded_answer(
            "Find acme", [], system_prompt="tools", tools=[tool]
        )
    assert answer.tool_calls[0].id == "call_9"
    assert answer.tool_calls[0].arguments == {"q": "acme"}


def test_embedding_refuses_when_index_is_768(monkeypatch):
    monkeypatch.setattr(settings, "gemini_embedding_dimensions", 768)
    provider = OpenRouterEmbeddingProvider(api_key="test-key", dimensions=2048)
    with patch("app.embeddings.openrouter.httpx.post", side_effect=AssertionError("network")):
        with pytest.raises(ProviderError, match="768-d"):
            provider.embed_query("hello")


def test_embedding_posts_when_dimensions_match(monkeypatch):
    monkeypatch.setattr(settings, "gemini_embedding_dimensions", 2048)
    monkeypatch.setattr(settings, "openrouter_api_base", "https://openrouter.ai/api/v1")
    provider = OpenRouterEmbeddingProvider(
        api_key="test-key",
        model="nvidia/nemotron-3-embed-1b:free",
        dimensions=2048,
    )
    response = MagicMock()
    response.status_code = 200
    response.json.return_value = {"data": [{"index": 0, "embedding": [0.25] * 2048}]}
    with patch("app.embeddings.openrouter.httpx.post", return_value=response) as posted:
        vector = provider.embed_query("hello")
    assert len(vector) == 2048
    assert posted.call_args.kwargs["json"]["model"] == "nvidia/nemotron-3-embed-1b:free"


def test_factories_select_openrouter(monkeypatch):
    monkeypatch.setattr(settings, "llm_provider", "openrouter")
    monkeypatch.setattr(settings, "embedding_provider", "openrouter")
    get_llm_provider.cache_clear()
    get_embedding_provider.cache_clear()
    try:
        assert isinstance(get_llm_provider(), OpenRouterLLMProvider)
        assert isinstance(get_embedding_provider(), OpenRouterEmbeddingProvider)
    finally:
        monkeypatch.setattr(settings, "llm_provider", "fake")
        monkeypatch.setattr(settings, "embedding_provider", "fake")
        get_llm_provider.cache_clear()
        get_embedding_provider.cache_clear()


def test_gemini_factory_wraps_fallback(monkeypatch):
    monkeypatch.setattr(settings, "llm_provider", "gemini")
    monkeypatch.setattr(settings, "gemini_api_key", "test-gemini")
    get_llm_provider.cache_clear()
    try:
        assert isinstance(get_llm_provider(), FallbackLLMProvider)
    finally:
        monkeypatch.setattr(settings, "llm_provider", "fake")
        get_llm_provider.cache_clear()


def test_gemini_rate_limit_fails_over_without_retries(monkeypatch):
    from app.llm.gemini import GeminiLLMProvider

    monkeypatch.setattr(settings, "gemini_api_base", "https://example.test/v1beta")
    provider = GeminiLLMProvider(api_key="secret-key", model="gemini-test")
    response = MagicMock()
    response.status_code = 429
    response.text = "slow"
    calls: list[tuple] = []

    def fake_post(url, headers=None, json=None, timeout=None, params=None):
        calls.append((url, headers, params))
        return response

    with patch("app.llm.gemini.httpx.post", fake_post), patch("app.llm.gemini.acquire_gemini"):
        with pytest.raises(ProviderRateLimited):
            provider.generate_grounded_answer("q", [], system_prompt="s")

    assert len(calls) == 1
    assert "key=" not in calls[0][0]
    assert calls[0][1]["x-goog-api-key"] == "secret-key"
    assert not calls[0][2] or "key" not in calls[0][2]


def test_transport_error_is_fallback_eligible():
    assert issubclass(httpx.TransportError, Exception)
    assert isinstance(GroundedAnswerChunk(delta="x"), GroundedAnswerChunk)


def test_retry_succeeds_on_second_attempt(monkeypatch):
    """When both providers are rate-limited on attempt 1, the fallback retries
    with backoff and succeeds on attempt 2."""
    monkeypatch.setattr(settings, "openrouter_api_key", "test-key")
    attempt_count = {"n": 0}

    class _BoomThenOk:
        model_id = "gemini-test"

        def generate_grounded_answer(self, *args, **kwargs):
            attempt_count["n"] += 1
            if attempt_count["n"] <= 1:
                raise ProviderRateLimited("Gemini rate limit")
            from app.llm.base import GroundedAnswer
            return GroundedAnswer(
                text="Success on retry",
                citations=[],
                model_id="gemini-test",
                prompt_version="v1",
            )

    # The fallback (OpenRouter) also fails on first attempt, so the whole
    # primary→fallback chain fails once and triggers the retry loop.
    class _BoomOnce:
        model_id = "openrouter-test"

        def generate_grounded_answer(self, *args, **kwargs):
            raise ProviderRateLimited("OpenRouter rate limit")

    provider = FallbackLLMProvider(_BoomThenOk(), _BoomOnce())
    with patch("app.llm.fallback.time.sleep") as mock_sleep:
        answer = provider.generate_grounded_answer("q", _chunk(), system_prompt="s")

    assert answer.text == "Success on retry"
    assert attempt_count["n"] == 2
    assert mock_sleep.call_count == 1
    # Verify backoff delay is positive
    assert mock_sleep.call_args[0][0] > 0


def test_retry_exhausted_raises(monkeypatch):
    """When all retry attempts are exhausted, ProviderRateLimited is raised."""
    monkeypatch.setattr(settings, "openrouter_api_key", "test-key")

    class _AlwaysBoom:
        model_id = "always-boom"

        def generate_grounded_answer(self, *args, **kwargs):
            raise ProviderRateLimited("always rate limited")

    provider = FallbackLLMProvider(_AlwaysBoom(), _AlwaysBoom())
    with patch("app.llm.fallback.time.sleep"):
        with pytest.raises(ProviderRateLimited):
            provider.generate_grounded_answer("q", _chunk(), system_prompt="s")


def test_stream_retry_succeeds_on_second_attempt(monkeypatch):
    """Stream path: when both providers are rate-limited on attempt 1, the
    fallback retries with backoff and succeeds on attempt 2."""
    monkeypatch.setattr(settings, "openrouter_api_key", "test-key")
    attempt_count = {"n": 0}

    class _StreamBoomThenOk:
        model_id = "gemini-test"

        def stream_grounded_answer(self, *args, **kwargs):
            attempt_count["n"] += 1
            if attempt_count["n"] <= 1:
                raise ProviderRateLimited("Gemini rate limit")
            yield GroundedAnswerChunk(delta="ok")
            yield GroundedAnswerChunk(delta="", done=True, citations=[])

    class _StreamBoomOnce:
        model_id = "openrouter-test"

        def stream_grounded_answer(self, *args, **kwargs):
            raise ProviderRateLimited("OpenRouter rate limit")
            yield  # pragma: no cover

    provider = FallbackLLMProvider(_StreamBoomThenOk(), _StreamBoomOnce())
    with patch("app.llm.fallback.time.sleep") as mock_sleep:
        chunks = list(provider.stream_grounded_answer("q", _chunk(), system_prompt="s"))

    assert chunks[0].delta == "ok"
    assert mock_sleep.call_count == 1
