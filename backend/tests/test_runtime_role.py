"""Restricted runtime grants and actionable production startup failures."""

from unittest.mock import MagicMock

import pytest
from sqlalchemy.dialects.postgresql import dialect

from app.db import migrate_cli


def _engine(role=(False, False, True), namespace=("defaultdb", "public")):
    engine = MagicMock()
    engine.dialect = dialect()
    conn = engine.begin.return_value.__enter__.return_value
    conn.execute.return_value.one_or_none.return_value = role
    conn.execute.return_value.one.return_value = namespace
    return engine, conn


def test_grants_existing_and_future_objects_without_admin_privileges():
    engine, conn = _engine()
    migrate_cli.grant_runtime_access(engine, "pka_app")
    calls = conn.execute.call_args_list
    assert calls[0].args[1] == {"role": "pka_app"}
    assert ":role" in str(calls[0].args[0])
    assert [str(call.args[0]) for call in calls[2:]] == [
        'GRANT CONNECT ON DATABASE "defaultdb" TO "pka_app"',
        'GRANT USAGE ON SCHEMA "public" TO "pka_app"',
        'GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA "public" TO "pka_app"',
        'GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA "public" TO "pka_app"',
        'ALTER DEFAULT PRIVILEGES IN SCHEMA "public" GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO "pka_app"',
        'ALTER DEFAULT PRIVILEGES IN SCHEMA "public" GRANT USAGE, SELECT ON SEQUENCES TO "pka_app"',
    ]


@pytest.mark.parametrize("role", [None, (True, False, True), (False, True, True), (False, False, False)])
def test_rejects_missing_or_unsafe_roles_before_granting(role):
    engine, conn = _engine(role=role)
    with pytest.raises(RuntimeError):
        migrate_cli.grant_runtime_access(engine, "avnadmin")
    assert conn.execute.call_count == 1


def test_quotes_all_identifiers():
    engine, conn = _engine(namespace=('db"name', 'schema"name'))
    migrate_cli.grant_runtime_access(engine, 'role"; DROP TABLE workspaces; --')
    grants = [str(call.args[0]) for call in conn.execute.call_args_list[2:]]
    assert grants[0] == 'GRANT CONNECT ON DATABASE "db""name" TO "role""; DROP TABLE workspaces; --"'
    assert '"schema""name"' in grants[1]


def test_rejects_non_postgres_and_missing_schema():
    engine, conn = _engine(namespace=("defaultdb", None))
    with pytest.raises(RuntimeError, match="no current schema"):
        migrate_cli.grant_runtime_access(engine, "pka_app")
    assert conn.execute.call_count == 2
    engine.dialect.name = "sqlite"
    with pytest.raises(RuntimeError, match="require PostgreSQL"):
        migrate_cli.grant_runtime_access(engine, "pka_app")


def test_migration_cli_grants_only_when_requested(monkeypatch):
    migrate = MagicMock()
    grants = MagicMock()
    monkeypatch.setattr(migrate_cli, "ensure_schema", migrate)
    monkeypatch.setattr(migrate_cli, "grant_runtime_access", grants)
    migrate_cli.main([])
    migrate.assert_called_once_with()
    grants.assert_not_called()
    migrate.reset_mock()
    migrate_cli.main(["--grant-runtime-role", "pka_app"])
    migrate.assert_called_once_with()
    grants.assert_called_once_with(migrate_cli.engine, "pka_app")


def test_migration_failure_never_grants_runtime_access(monkeypatch):
    def fail():
        raise RuntimeError("migration failed")

    grants = MagicMock()
    monkeypatch.setattr(migrate_cli, "ensure_schema", fail)
    monkeypatch.setattr(migrate_cli, "grant_runtime_access", grants)
    with pytest.raises(RuntimeError, match="migration failed"):
        migrate_cli.main(["--grant-runtime-role", "pka_app"])
    grants.assert_not_called()


def test_rls_failure_explains_recovery_without_disabling_security(monkeypatch):
    from app.db.rls import check_rls_posture

    engine, _ = _engine()
    monkeypatch.setattr("app.db.rls.rls_posture", lambda _: {
        "role": "avnadmin", "bypassrls": True, "enforced": False,
    })
    with pytest.raises(RuntimeError) as error:
        check_rls_posture(engine, required=True)
    message = str(error.value)
    assert "BYPASSRLS" in message
    assert "--grant-runtime-role pka_app" in message
    assert "DATABASE_URL" in message
    assert "Keep RLS_REQUIRED=true" in message
