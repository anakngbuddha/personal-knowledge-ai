from app.llm.limiter import TokenBucket, acquire_gemini
from app.ocr.factory import get_ocr_provider
from app.ocr.fake import FakeOcrProvider
from app.ocr.null import NullOcrProvider


def test_null_ocr_is_unavailable():
    provider = NullOcrProvider()
    assert provider.available is False
    assert provider.image_to_text(b"x") == ""


def test_fake_ocr_returns_text():
    provider = FakeOcrProvider("hello")
    assert provider.available is True
    assert provider.image_to_text(b"png") == "hello"


def test_factory_fake_provider(monkeypatch):
    from app.core.config import settings

    monkeypatch.setattr(settings, "ocr_provider", "fake")
    get_ocr_provider.cache_clear()
    try:
        provider = get_ocr_provider()
        assert isinstance(provider, FakeOcrProvider)
        assert provider.available is True
    finally:
        get_ocr_provider.cache_clear()


def test_token_bucket_allows_immediate_first_call():
    bucket = TokenBucket(rate_per_minute=600)
    bucket.acquire()
    acquire_gemini()
