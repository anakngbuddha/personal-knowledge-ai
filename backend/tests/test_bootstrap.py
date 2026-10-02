"""Schema bootstrap on API boot (Render / production)."""

from unittest.mock import MagicMock

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


@pytest.mark.parametrize("repair_fails", [False, True])
def test_admin_bootstrap_reconciles_recorded_migrations_before_seed_and_grants(monkeypatch, repair_fails):
    from sqlalchemy.dialects.postgresql import dialect
    from app.db import bootstrap, migrate_cli

    engine = MagicMock()
    engine.dialect = dialect()
    steps = MagicMock()
    steps.migrate.return_value = []  # Every migration is already recorded.
    if repair_fails:
        steps.repair.side_effect = RuntimeError("RLS reconciliation failed")
    monkeypatch.setattr(bootstrap, "engine", engine)
    monkeypatch.setattr(bootstrap.Base.metadata, "create_all", steps.create)
    monkeypatch.setattr(bootstrap, "run_migrations", steps.migrate)
    monkeypatch.setattr(bootstrap, "reconcile_rls", steps.repair)
    monkeypatch.setattr(bootstrap, "system_session", steps.session)
    monkeypatch.setattr("app.security.deps.get_or_create_default_org", steps.org)
    monkeypatch.setattr("app.documents.service.get_or_create_default_workspace", steps.workspace)
    monkeypatch.setattr(migrate_cli, "grant_runtime_access", steps.grant)

    if repair_fails:
        with pytest.raises(RuntimeError, match="RLS reconciliation failed"):
            migrate_cli.main(["--grant-runtime-role", "pka_app"])
        steps.session.assert_not_called()
        steps.org.assert_not_called()
        steps.grant.assert_not_called()
    else:
        migrate_cli.main(["--grant-runtime-role", "pka_app"])
        names = [c[0] for c in steps.mock_calls]
        assert names.index("migrate") < names.index("repair") < names.index("session")
        assert names.index("workspace") < names.index("grant")
        steps.session.return_value.close.assert_called_once()
    steps.repair.assert_called_once_with(engine)


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
