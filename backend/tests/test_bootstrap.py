"""Schema bootstrap on API boot (Render / production)."""

import pytest

from app.core.config import settings
from app.db.bootstrap import ensure_schema, should_bootstrap


def test_dev_and_pytest_do_not_bootstrap_on_lifespan():
    assert settings.environment.lower() not in {"production", "prod"}
    assert settings.auto_migrate is False
    assert should_bootstrap() is False


def test_production_environment_enables_bootstrap(monkeypatch):
    monkeypatch.setattr(settings, "environment", "production")
    monkeypatch.setattr(settings, "auto_migrate", False)
    assert should_bootstrap() is False
    monkeypatch.setattr(settings, "environment", "development")
    monkeypatch.setattr(settings, "auto_migrate", True)
    assert should_bootstrap() is True
    monkeypatch.setattr(settings, "auto_migrate", False)
    assert should_bootstrap() is False


def test_required_rls_posture_blocks_bypass_role(monkeypatch):
    from types import SimpleNamespace
    from app.db.rls import check_rls_posture
    monkeypatch.setattr("app.db.rls.rls_posture", lambda _engine: {
        "role": "avnadmin", "superuser": False, "bypassrls": True,
        "unprotected_tables": [], "enforced": False,
    })
    engine = SimpleNamespace(dialect=SimpleNamespace(name="postgresql"))
    with pytest.raises(RuntimeError, match="BYPASSRLS"):
        check_rls_posture(engine, required=True)


@pytest.mark.requires_db
def test_ensure_schema_creates_workflow_tables(database):
    from sqlalchemy import inspect

    ensure_schema()
    ensure_schema()
    names = inspect(database).get_table_names()
    assert "task_executions" in names
    assert "workflow_runs" in names
    assert "mcp_integrations" in names
    assert "notes" in names
    assert "vendor_sources" in names
    assert "restore_drills" in names
    assert "sso_providers" in names
    assert "schema_migrations" in names
