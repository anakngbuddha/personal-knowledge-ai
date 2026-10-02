"""Administrator RLS repair, rollback/retry behavior, and catalog validation."""

from types import SimpleNamespace
from unittest.mock import MagicMock, call

import pytest
from sqlalchemy.dialects.postgresql import dialect
from sqlalchemy.exc import DBAPIError

from app.db import migrations, rls


def _engine():
    engine = MagicMock()
    engine.dialect = dialect()
    return engine


def _catalog(engine, rows, policies, role=("pka_app", False, False)):
    results = [MagicMock() for _ in range(3)]
    results[0].one.return_value = role
    results[1].all.return_value = rows
    results[2].all.return_value = policies
    engine.connect.return_value.__enter__.return_value.execute.side_effect = results


@pytest.mark.parametrize("enabled,forced", [(False, False), (True, False), (False, True)])
def test_posture_reports_missing_rls_flags(enabled, forced):
    engine = _engine()
    expression = migrations._RLS_PREDICATE
    _catalog(engine, [("organization_memberships", enabled, forced)], [
        ("organization_memberships", "tenant_isolation", expression, expression),
    ])
    posture = rls.rls_posture(engine)
    assert posture["unprotected_tables"] == ["organization_memberships"]
    assert posture["enforced"] is False


@pytest.mark.parametrize("using,check", [
    (migrations._RLS_PREDICATE + " OR org_id IS NULL", migrations._RLS_PREDICATE),
    (migrations._RLS_PREDICATE, migrations._RLS_PREDICATE + " OR org_id IS NULL"),
    (migrations._RLS_PREDICATE, None),
])
def test_posture_rejects_legacy_or_missing_write_predicates(using, check):
    engine = _engine()
    _catalog(engine, [("workspaces", True, True)], [
        ("workspaces", "tenant_isolation", using, check),
    ])
    posture = rls.rls_posture(engine)
    assert posture["invalid_policy_tables"] == ["workspaces"]
    assert posture["invalid_policy_names"] == {"workspaces": ["tenant_isolation"]}
    assert posture["enforced"] is False


def test_posture_names_unexpected_policies_and_missing_derived_policy():
    engine = _engine()
    expression = migrations._RLS_PREDICATE
    _catalog(engine, [("messages", True, True), ("workspaces", True, True)], [
        ("workspaces", "tenant_isolation", expression, expression),
        ("workspaces", "custom_share", "true", "true"),
    ])
    posture = rls.rls_posture(engine)
    assert posture["invalid_policy_names"] == {
        "messages": [], "workspaces": ["custom_share", "tenant_isolation"],
    }
    assert posture["enforced"] is False


def test_posture_accepts_postgres_deparsed_offline_policy():
    engine = _engine()
    expression = "(current_setting('app.rls_bypass'::text, true) = 'on'::text)"
    _catalog(engine, [("evaluation_questions", True, True)], [
        ("evaluation_questions", "tenant_isolation", expression, expression),
    ])
    assert rls.check_rls_posture(engine, required=True)["enforced"] is True


def test_reconciliation_verifies_tables_without_requiring_a_restricted_admin(monkeypatch):
    engine = _engine()
    steps = MagicMock()
    monkeypatch.setattr(migrations, "_apply_rls", steps.direct)
    monkeypatch.setattr(migrations, "_apply_derived_rls", steps.derived)
    monkeypatch.setattr(rls, "rls_posture", steps.posture)
    steps.posture.return_value = {
        "superuser": True, "bypassrls": True, "enforced": False,
        "unprotected_tables": [], "invalid_policy_tables": [],
    }
    migrations.reconcile_rls(engine)
    assert steps.mock_calls == [call.direct(engine), call.derived(engine), call.posture(engine)]


def test_reconciliation_skips_non_postgres(monkeypatch):
    engine = SimpleNamespace(dialect=SimpleNamespace(name="sqlite"))
    repair = MagicMock()
    monkeypatch.setattr(migrations, "_apply_rls", repair)
    migrations.reconcile_rls(engine)
    repair.assert_not_called()


def test_reconciliation_aborts_with_table_and_policy_names(monkeypatch):
    engine = _engine()
    monkeypatch.setattr(migrations, "_apply_rls", MagicMock())
    monkeypatch.setattr(migrations, "_apply_derived_rls", MagicMock())
    monkeypatch.setattr(rls, "rls_posture", lambda _: {
        "unprotected_tables": ["messages"],
        "invalid_policy_tables": ["evaluation_questions", "workspaces"],
        "invalid_policy_names": {"evaluation_questions": [], "workspaces": ["custom_share", "tenant_isolation"]},
    })
    with pytest.raises(RuntimeError, match="RLS reconciliation failed") as failure:
        migrations.reconcile_rls(engine)
    message = str(failure.value)
    assert "tables without ENABLE+FORCE RLS: messages" in message
    assert "evaluation_questions (missing tenant_isolation)" in message
    assert "workspaces (custom_share, tenant_isolation)" in message
    assert "preserved" in message
    assert "Keep RLS_REQUIRED=true" in message


def test_derived_repairs_use_current_schema_and_preserve_offline_default_deny():
    engine = _engine()
    engine.connect.return_value.__enter__.return_value.scalar.return_value = 'private"schema'
    migrations._apply_derived_rls(engine)
    statements = [str(c.args[0]) for c in engine.begin.return_value.__enter__.return_value.execute.call_args_list]
    creates = [sql for sql in statements if sql.startswith("CREATE POLICY")]
    assert len(creates) == 4
    assert all('ON "private""schema".' in sql for sql in creates)
    offline = next(sql for sql in creates if '."evaluation_questions"' in sql)
    assert " OR " not in offline
    assert "WITH CHECK (current_setting('app.rls_bypass', true) = 'on')" in offline
    assert not any(sql.startswith("DROP POLICY") and "tenant_isolation" not in sql for sql in statements)


def test_derived_repairs_reject_missing_schema():
    engine = _engine()
    engine.connect.return_value.__enter__.return_value.scalar.return_value = None
    with pytest.raises(RuntimeError, match="no current schema"):
        migrations._apply_derived_rls(engine)
    engine.begin.assert_not_called()


@pytest.mark.parametrize("state,failures", [("40P01", 1), ("55P03", 2), ("55P03", 5), ("42501", 1)])
def test_policy_repair_rolls_back_and_bounds_retries(monkeypatch, state, failures):
    engine = _engine()
    transactions = [MagicMock() for _ in range(failures + 1)]
    error = DBAPIError("CREATE POLICY", {}, SimpleNamespace(sqlstate=state))
    for transaction in transactions[:failures]:
        transaction.__enter__.return_value.execute.side_effect = [None] * 5 + [error]
    engine.begin.side_effect = transactions
    sleep = MagicMock()
    monkeypatch.setattr(migrations.time, "sleep", sleep)
    if state == "42501" or failures == 5:
        with pytest.raises(DBAPIError):
            migrations._apply_rls_table(engine, "public", "messages", predicate="false")
        attempts = 1 if state == "42501" else 5
    else:
        migrations._apply_rls_table(engine, "public", "messages", predicate="false")
        attempts = failures + 1
    assert engine.begin.call_count == attempts
    assert sleep.call_args_list == [call(min(2 ** i, 8)) for i in range(attempts - 1)]
    for transaction in transactions[:min(failures, attempts)]:
        assert transaction.__exit__.call_args.args[:2] == (DBAPIError, error)
