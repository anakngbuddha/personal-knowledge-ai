"""PostgreSQL row-level security (audit findings 4 and 15).

The SQLite isolation suite proves the application filters; it cannot prove RLS. These
tests run against the CI PostgreSQL service and switch to a NOSUPERUSER NOBYPASSRLS
role, because a superuser (the CI default) ignores every policy.
"""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy import create_engine, event, text
from sqlalchemy.exc import DBAPIError

pytestmark = pytest.mark.requires_db

PROBE = "pka_rls_probe"


@pytest.fixture
def probe(database):
    with database.begin() as conn:
        conn.execute(
            text(
                "DO $$ BEGIN IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'pka_rls_probe') "
                "THEN CREATE ROLE pka_rls_probe NOLOGIN NOSUPERUSER NOBYPASSRLS; END IF; END $$"
            )
        )
        conn.execute(text("GRANT USAGE ON SCHEMA public TO pka_rls_probe"))
        conn.execute(text("GRANT SELECT, INSERT, UPDATE, DELETE ON workspaces TO pka_rls_probe"))
    return database


@pytest.fixture
def tenants(probe):
    from app.db.models import Organization, Workspace
    from app.db.session import system_session

    db = system_session()
    org_a = Organization(id=uuid.uuid4(), slug=f"rls-a-{uuid.uuid4().hex[:8]}", name="A")
    org_b = Organization(id=uuid.uuid4(), slug=f"rls-b-{uuid.uuid4().hex[:8]}", name="B")
    db.add_all([org_a, org_b])
    db.commit()
    ws_a = Workspace(id=uuid.uuid4(), org_id=org_a.id, name="A")
    ws_b = Workspace(id=uuid.uuid4(), org_id=org_b.id, name="B")
    db.add_all([ws_a, ws_b])
    db.commit()
    ids = {"org_a": org_a.id, "org_b": org_b.id, "ws_a": ws_a.id, "ws_b": ws_b.id}
    try:
        yield ids
    finally:
        db.delete(ws_a)
        db.delete(ws_b)
        db.commit()
        db.delete(org_a)
        db.delete(org_b)
        db.commit()
        db.close()


def _visible(engine, ids, *, org: str, bypass: str = "off") -> set[uuid.UUID]:
    with engine.connect() as conn:
        trans = conn.begin()
        try:
            conn.execute(text(f"SET LOCAL ROLE {PROBE}"))
            conn.execute(
                text("SELECT set_config('app.current_org_id', :org, true), set_config('app.rls_bypass', :bypass, true)"),
                {"org": org, "bypass": bypass},
            )
            rows = conn.execute(
                text("SELECT org_id FROM workspaces WHERE id IN (:a, :b)"),
                {"a": ids["ws_a"], "b": ids["ws_b"]},
            ).scalars().all()
            return {uuid.UUID(str(r)) for r in rows}
        finally:
            trans.rollback()


def test_policy_scopes_rows_to_the_current_org(probe, tenants):
    assert _visible(probe, tenants, org=str(tenants["org_a"])) == {tenants["org_a"]}
    assert _visible(probe, tenants, org=str(tenants["org_b"])) == {tenants["org_b"]}


def test_wrong_or_missing_org_sees_nothing(probe, tenants):
    assert _visible(probe, tenants, org=str(uuid.uuid4())) == set()
    assert _visible(probe, tenants, org="") == set()


def test_system_bypass_sees_everything(probe, tenants):
    assert _visible(probe, tenants, org="", bypass="on") == {tenants["org_a"], tenants["org_b"]}


def test_insert_into_another_org_is_refused(probe, tenants):
    with probe.connect() as conn:
        trans = conn.begin()
        try:
            conn.execute(text(f"SET LOCAL ROLE {PROBE}"))
            conn.execute(
                text("SELECT set_config('app.current_org_id', :org, true), set_config('app.rls_bypass', 'off', true)"),
                {"org": str(tenants["org_a"])},
            )
            with pytest.raises(DBAPIError):
                conn.execute(
                    text("INSERT INTO workspaces (id, org_id, name) VALUES (:id, :org, 'x')"),
                    {"id": uuid.uuid4(), "org": tenants["org_b"]},
                )
        finally:
            trans.rollback()


def test_tenant_session_helper_applies_scope_after_commit(probe, tenants):
    from app.db.session import get_tenant_db

    gen = get_tenant_db(tenants["org_a"])
    session = next(gen)
    try:
        session.commit()  # the old SET LOCAL helper lost its scope here
        session.execute(text(f"SET LOCAL ROLE {PROBE}"))
        rows = session.execute(
            text("SELECT org_id FROM workspaces WHERE id IN (:a, :b)"),
            {"a": tenants["ws_a"], "b": tenants["ws_b"]},
        ).scalars().all()
        assert {uuid.UUID(str(r)) for r in rows} == {tenants["org_a"]}
    finally:
        session.rollback()
        gen.close()


def test_every_tenant_table_is_enabled_and_forced(probe):
    from app.db.rls import rls_posture

    posture = rls_posture(probe)
    assert posture["unprotected_tables"] == []


def test_null_tenant_rows_are_not_shared(probe, tenants):
    row_id = uuid.uuid4()
    with probe.connect() as conn:
        transaction = conn.begin()
        try:
            conn.execute(text("INSERT INTO workspaces (id, org_id, name) VALUES (:id, NULL, 'quarantined')"), {"id": row_id})
            conn.execute(text(f"SET LOCAL ROLE {PROBE}"))
            conn.execute(text("SELECT set_config('app.current_org_id', :org, true), set_config('app.rls_bypass', 'off', true)"), {"org": str(tenants["org_a"])})
            assert conn.scalar(text("SELECT id FROM workspaces WHERE id = :id"), {"id": row_id}) is None
        finally:
            transaction.rollback()


def test_derived_tables_have_forced_rls(probe):
    with probe.connect() as conn:
        for table in ("messages", "product_capabilities", "reference_architecture_products", "organization_memberships", "evaluation_questions"):
            assert conn.scalar(text("SELECT relrowsecurity AND relforcerowsecurity FROM pg_class WHERE oid = to_regclass(:table)"), {"table": table}) is True


def test_tenant_reassignment_is_rejected_even_for_system(probe, tenants):
    with pytest.raises(DBAPIError):
        with probe.begin() as conn:
            conn.execute(text("UPDATE workspaces SET org_id=:other WHERE id=:id"), {"other": tenants["org_b"], "id": tenants["ws_a"]})


def test_migration_repairs_a_partially_applied_table(probe):
    from app.db.migrations import _apply_rls_table

    try:
        with probe.begin() as conn:
            conn.execute(text("ALTER TABLE workspaces NO FORCE ROW LEVEL SECURITY"))

        _apply_rls_table(probe, "public", "workspaces")
        _apply_rls_table(probe, "public", "workspaces")  # already complete

        with probe.connect() as conn:
            assert conn.scalar(
                text("SELECT relrowsecurity AND relforcerowsecurity "
                     "FROM pg_class WHERE oid = 'public.workspaces'::regclass")
            ) is True
    finally:
        # Keep the shared database protected even when the assertion fails.
        _apply_rls_table(probe, "public", "workspaces")


def test_unscoped_app_session_is_default_deny(probe, tenants):
    from app.db.session import get_db

    gen = get_db()
    session = next(gen)
    try:
        session.execute(text(f"SET LOCAL ROLE {PROBE}"))
        rows = session.execute(
            text("SELECT org_id FROM workspaces WHERE id IN (:a, :b)"),
            {"a": tenants["ws_a"], "b": tenants["ws_b"]},
        ).all()
        assert rows == []
    finally:
        session.rollback()
        gen.close()


@pytest.fixture
def runtime_probe(probe):
    # information_schema must expose every tenant table to the posture checker.
    with probe.begin() as conn:
        conn.execute(text("GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO pka_rls_probe"))
    runtime = create_engine(probe.url)

    @event.listens_for(runtime, "connect")
    def restrict_connection(connection, _record):
        with connection.cursor() as cursor:
            cursor.execute("SET ROLE pka_rls_probe")
        connection.commit()

    try:
        yield runtime
    finally:
        runtime.dispose()


def test_admin_bootstrap_repairs_render_failure_with_completed_history(probe, runtime_probe, tenants):
    from app.db.bootstrap import ensure_schema
    from app.db.migrations import applied_migrations
    from app.db.rls import check_rls_posture

    ensure_schema()
    recorded = applied_migrations(probe)
    legacy = (
        "current_setting('app.rls_bypass', true) = 'on' OR org_id IS NULL "
        "OR CAST(org_id AS text) = current_setting('app.current_org_id', true)"
    )
    try:
        with probe.begin() as conn:
            conn.execute(text("DROP POLICY tenant_isolation ON workspaces"))
            conn.execute(text(f"CREATE POLICY tenant_isolation ON workspaces USING ({legacy}) WITH CHECK ({legacy})"))
            for table in ("messages", "product_capabilities", "reference_architecture_products", "evaluation_questions", "organization_memberships"):
                conn.execute(text(f"ALTER TABLE {table} NO FORCE ROW LEVEL SECURITY"))
                conn.execute(text(f"ALTER TABLE {table} DISABLE ROW LEVEL SECURITY"))
            conn.execute(text("DROP POLICY tenant_isolation ON messages"))

        with pytest.raises(RuntimeError, match="row-level security is NOT enforced"):
            check_rls_posture(runtime_probe, required=True)

        assert ensure_schema() == []
        assert ensure_schema() == []
        assert applied_migrations(probe) == recorded
        posture = check_rls_posture(runtime_probe, required=True)
        assert posture["enforced"] is True
        assert posture["unprotected_tables"] == []
        assert posture["invalid_policy_tables"] == []
        assert _visible(probe, tenants, org=str(tenants["org_a"])) == {tenants["org_a"]}
        assert _visible(probe, tenants, org="") == set()

        # Exercise the repaired derived policy with real parent and message rows.
        conversation_a, conversation_b = uuid.uuid4(), uuid.uuid4()
        message_a, message_b = uuid.uuid4(), uuid.uuid4()
        with probe.begin() as conn:
            for conversation, message, org, workspace in (
                (conversation_a, message_a, tenants["org_a"], tenants["ws_a"]),
                (conversation_b, message_b, tenants["org_b"], tenants["ws_b"]),
            ):
                conn.execute(text("INSERT INTO conversations (id, org_id, workspace_id) VALUES (:id, :org, :workspace)"),
                             {"id": conversation, "org": org, "workspace": workspace})
                conn.execute(text("INSERT INTO messages (id, conversation_id, role, content, refused) VALUES (:id, :conversation, 'user', 'test', false)"),
                             {"id": message, "conversation": conversation})
        with runtime_probe.begin() as conn:
            conn.execute(text("SELECT set_config('app.current_org_id', :org, true), set_config('app.rls_bypass', 'off', true)"),
                         {"org": str(tenants["org_a"])})
            visible = conn.execute(text("SELECT id FROM messages WHERE id IN (:a, :b)"), {"a": message_a, "b": message_b}).scalars().all()
            assert {uuid.UUID(str(value)) for value in visible} == {message_a}
        with pytest.raises(DBAPIError):
            with runtime_probe.begin() as conn:
                conn.execute(text("SELECT set_config('app.current_org_id', :org, true), set_config('app.rls_bypass', 'off', true)"),
                             {"org": str(tenants["org_a"])})
                conn.execute(text("INSERT INTO messages (id, conversation_id, role, content, refused) VALUES (:id, :conversation, 'user', 'forbidden', false)"),
                             {"id": uuid.uuid4(), "conversation": conversation_b})
    finally:
        ensure_schema()


def test_interrupted_reconciliation_can_resume(probe, runtime_probe, monkeypatch):
    from app.db import migrations
    from app.db.rls import check_rls_posture

    repair_table = migrations._apply_rls_table

    def interrupt(engine, schema, name, **kwargs):
        if name == "evaluation_questions":
            raise RuntimeError("interrupted derived repair")
        return repair_table(engine, schema, name, **kwargs)

    try:
        with probe.begin() as conn:
            conn.execute(text("ALTER TABLE workspaces NO FORCE ROW LEVEL SECURITY"))
            conn.execute(text("ALTER TABLE messages DISABLE ROW LEVEL SECURITY"))
        with monkeypatch.context() as patch:
            patch.setattr(migrations, "_apply_rls_table", interrupt)
            with pytest.raises(RuntimeError, match="interrupted derived repair"):
                migrations.reconcile_rls(probe)
        with probe.connect() as conn:
            assert conn.scalar(text("SELECT relrowsecurity AND relforcerowsecurity FROM pg_class WHERE oid='public.workspaces'::regclass")) is True
            assert conn.scalar(text("SELECT relrowsecurity AND relforcerowsecurity FROM pg_class WHERE oid='public.messages'::regclass")) is True
        migrations.reconcile_rls(probe)
        assert check_rls_posture(runtime_probe, required=True)["enforced"] is True
    finally:
        migrations.reconcile_rls(probe)


def test_reconciliation_preserves_and_reports_custom_policies(probe):
    from app.db.migrations import reconcile_rls

    try:
        with probe.begin() as conn:
            conn.execute(text("CREATE POLICY custom_share ON workspaces USING (true) WITH CHECK (true)"))
        with pytest.raises(RuntimeError, match=r"workspaces \(custom_share, tenant_isolation\)"):
            reconcile_rls(probe)
        with probe.connect() as conn:
            assert conn.scalar(text("SELECT count(*) FROM pg_policy WHERE polrelid='public.workspaces'::regclass AND polname='custom_share'")) == 1
    finally:
        with probe.begin() as conn:
            conn.execute(text("DROP POLICY IF EXISTS custom_share ON workspaces"))
        reconcile_rls(probe)


def test_reconciled_offline_questions_require_system_scope(probe, runtime_probe, tenants):
    from app.db.migrations import reconcile_rls

    question = uuid.uuid4()
    reconcile_rls(probe)
    try:
        with probe.begin() as conn:
            conn.execute(text("INSERT INTO evaluation_questions (id, question) VALUES (:id, 'offline test')"), {"id": question})
        for bypass in ("off", "on"):
            with runtime_probe.begin() as conn:
                conn.execute(text("SELECT set_config('app.current_org_id', :org, true), set_config('app.rls_bypass', :bypass, true)"),
                             {"org": str(tenants["org_a"]), "bypass": bypass})
                visible = conn.scalar(text("SELECT id FROM evaluation_questions WHERE id=:id"), {"id": question})
                assert (visible is not None) == (bypass == "on")
        with pytest.raises(DBAPIError):
            with runtime_probe.begin() as conn:
                conn.execute(text("SELECT set_config('app.rls_bypass', 'off', true)"))
                conn.execute(text("INSERT INTO evaluation_questions (id, question) VALUES (:id, 'forbidden')"), {"id": uuid.uuid4()})
    finally:
        with probe.begin() as conn:
            conn.execute(text("DELETE FROM evaluation_questions WHERE id=:id"), {"id": question})
