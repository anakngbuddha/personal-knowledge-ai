"""Tenant guard DDL must be atomic, observable, and bounded under contention."""

from types import SimpleNamespace
from unittest.mock import MagicMock, call

import pytest
from sqlalchemy.dialects.postgresql import dialect
from sqlalchemy.exc import DBAPIError

from app.db import tenant_constraints as guards


@pytest.mark.parametrize("state,failures", [
    ("40P01", 1), ("55P03", 2), ("55P03", 5), ("42501", 1), ("57014", 1),
])
def test_guard_replacement_rolls_back_and_bounds_retries(monkeypatch, state, failures, caplog):
    engine = MagicMock()
    transactions = [MagicMock() for _ in range(failures + 1)]
    error = DBAPIError("CREATE TRIGGER", {}, SimpleNamespace(sqlstate=state))
    for transaction in transactions[:failures]:
        transaction.__enter__.return_value.execute.side_effect = [None] * 3 + [error]
    engine.begin.side_effect = transactions
    sleep = MagicMock()
    monkeypatch.setattr(guards.time, "sleep", sleep)
    statements = ["DROP TRIGGER IF EXISTS tenant_parent ON workspaces", "CREATE TRIGGER tenant_parent"]
    if state not in guards._RETRYABLE_STATES:
        with pytest.raises(DBAPIError):
            guards._apply_guard_statements(engine, statements, '"workspaces"')
        attempts = 1
    elif failures == 5:
        with pytest.raises(RuntimeError, match='blocked for "workspaces" after 5 attempts') as failure:
            guards._apply_guard_statements(engine, statements, '"workspaces"')
        assert failure.value.__cause__ is error
        assert "pg_blocking_pids()" in str(failure.value)
        attempts = 5
    else:
        guards._apply_guard_statements(engine, statements, '"workspaces"')
        attempts = failures + 1
    assert engine.begin.call_count == attempts
    assert sleep.call_args_list == [call(min(2 ** i, 8)) for i in range(attempts - 1)]
    for transaction in transactions[:min(failures, attempts)]:
        assert transaction.__exit__.call_args.args[:2] == (DBAPIError, error)
        first = transaction.__enter__.return_value.execute.call_args_list[0]
        assert "set_config('lock_timeout', :lock_timeout, true)" in str(first.args[0])
        assert "set_config('statement_timeout', :statement_timeout, true)" in str(first.args[0])
        assert first.args[1] == {"lock_timeout": "5s", "statement_timeout": "30s"}
    if attempts > 1:
        assert 'waiting for "workspaces"' in caplog.text


def test_all_guards_for_each_table_are_replaced_in_one_transaction(monkeypatch):
    engine = MagicMock()
    engine.dialect = dialect()
    inspector = MagicMock()
    inspector.get_table_names.return_value = ["children", "parents", "identity"]
    inspector.get_columns.side_effect = lambda table: [
        {"name": name} for name in ({"id"} if table == "identity" else {"id", "org_id"})
    ]
    inspector.get_foreign_keys.side_effect = lambda table: [
        {"referred_table": "parents", "constrained_columns": ["parent_id"], "referred_columns": ["id"]},
        {"referred_table": "identity", "constrained_columns": ["user_id"], "referred_columns": ["id"]},
        {"referred_table": "parents", "constrained_columns": ["a", "b"], "referred_columns": ["a", "b"]},
    ] if table == "children" else []
    monkeypatch.setattr(guards, "inspect", lambda _: inspector)
    apply = MagicMock()
    monkeypatch.setattr(guards, "_apply_guard_statements", apply)
    guards.apply_parent_guards(engine)
    assert [c.args[2] for c in apply.call_args_list] == ["trigger functions", '"children"', '"parents"']
    child_statements = apply.call_args_list[1].args[1]
    assert len(child_statements) == 4
    assert "tenant_immutable" in child_statements[0]
    assert "tenant_parent_parent_id" in child_statements[2]
    assert not any("tenant_parent_user_id" in sql for sql in child_statements)


def test_migration_cli_logs_progress_before_database_work(monkeypatch, caplog):
    from app.db import migrate_cli

    caplog.set_level("INFO", logger="app.db.migrate_cli")

    def migrate():
        assert "starting administrator schema migration" in caplog.text

    monkeypatch.setattr(migrate_cli, "ensure_schema", migrate)
    migrate_cli.main([])
