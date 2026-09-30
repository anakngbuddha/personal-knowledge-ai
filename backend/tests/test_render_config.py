"""Keep the Render deployment compatible with production settings validation."""

from pathlib import Path

import pytest
import yaml
from pydantic import ValidationError

from app.core.config import Settings


def test_render_blueprint_passes_production_security_validation(monkeypatch):
    blueprint = Path(__file__).resolve().parents[2] / "render.yaml"
    services = yaml.safe_load(blueprint.read_text(encoding="utf-8"))["services"]
    service = next(s for s in services if s["name"] == "personal-knowledge-ai-api")
    variables = service["envVars"]
    # Exercise actual environment parsing, including string boolean values.
    for variable in variables:
        monkeypatch.delenv(variable["key"], raising=False)
        if "value" in variable:
            monkeypatch.setenv(variable["key"], str(variable["value"]))
    monkeypatch.setenv("JWT_SECRET_KEY", "test-only-secret-" * 3)
    config = Settings(_env_file=None)
    assert config.environment == "production"
    assert config.rls_required is True
    assert config.rls_default_deny is True
    assert config.auto_migrate is False
    assert config.allow_legacy_token_endpoint is False

    # A deployment override must never disable the production security gate.
    monkeypatch.setenv("RLS_REQUIRED", "false")
    with pytest.raises(ValidationError, match="RLS_REQUIRED"):
        Settings(_env_file=None)
