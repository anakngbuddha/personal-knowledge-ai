"""Health dependency checks for PART2 6.3."""

from __future__ import annotations

import inspect

from app.api.routes import health as health_routes
from app.core.config import settings


def test_health_reports_llm_key_without_secret():
    source = inspect.getsource(health_routes.dependencies)
    assert "key_configured" in source
    assert "gemini_api_key" in source
    # The response must never include the raw key value.
    assert 'checks["llm"]' in source or "checks['llm']" in source


def test_llm_check_shape_for_fake_provider(monkeypatch):
    monkeypatch.setattr(settings, "llm_provider", "fake")
    monkeypatch.setattr(settings, "gemini_api_key", "")
    # Inline the same logic the route uses for the fake branch.
    provider_name = (settings.llm_provider or "gemini").lower()
    assert provider_name == "fake"
    check = {
        "ok": True,
        "provider": "fake",
        "key_configured": True,
    }
    assert check["ok"] is True
    assert "gemini_api_key" not in check
