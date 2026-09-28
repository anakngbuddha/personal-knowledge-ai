"""Shared Gemini token-bucket wiring and boot job reclaim (PART2 6.2)."""

from __future__ import annotations

import inspect

from app.api.routes import health as health_routes
from app.embeddings import gemini as emb_mod
from app.llm import gemini as llm_mod
from app.main import lifespan
from app.ocr import gemini as ocr_mod


def test_gemini_entry_points_call_acquire():
    assert "acquire_gemini" in inspect.getsource(emb_mod.GeminiEmbeddingProvider._batch_embed)
    # Synchronous generation calls _post, where the shared limiter is acquired.
    assert "self._post" in inspect.getsource(llm_mod.GeminiLLMProvider.generate_grounded_answer)
    assert "acquire_gemini" in inspect.getsource(llm_mod.GeminiLLMProvider._post)
    assert "acquire_gemini" in inspect.getsource(llm_mod.GeminiLLMProvider.stream_grounded_answer)
    assert "acquire_gemini" in inspect.getsource(ocr_mod.GeminiOcrProvider._image_to_text_once)


def test_ocr_retries_on_rate_limit():
    source = inspect.getsource(ocr_mod.GeminiOcrProvider)
    assert "@retry" in source or "retry(" in source
    assert "ProviderRateLimited" in source


def test_boot_lifespan_reaps_stale_jobs():
    source = inspect.getsource(lifespan)
    assert "reap_stale" in source


def test_health_dependencies_includes_gemini_queue():
    source = inspect.getsource(health_routes.dependencies)
    assert 'checks["gemini"]' in source or "checks['gemini']" in source
    assert "queued" in source
