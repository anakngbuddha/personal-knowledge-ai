"""PostgreSQL row-level security (audit findings 4 and 15).

The SQLite isolation suite proves the application filters; it cannot prove RLS. These
tests run against the CI PostgreSQL service and switch to a NOSUPERUSER NOBYPASSRLS
role, because a superuser (the CI default) ignores every policy.
"""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy import text
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
