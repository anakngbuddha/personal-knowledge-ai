"""HITL approve/reject API tests."""

from __future__ import annotations

import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.models import (
    AuditLog,
    Base,
    Organization,
    TaskExecution,
    TaskStatus,
    WorkflowRun,
    Workspace,
)
from app.db.session import get_db
from app.main import app
from app.security.jwt import mint_token
from app.security.labels import Role
from app.workflows.loader import load_playbook
from app.workflows.queue import claim, start_run, succeed, waiting_approval

client = TestClient(app)


@compiles(JSONB, "sqlite")
def _compile_jsonb_sqlite(element, compiler, **kw):
    return "JSON"


@pytest.fixture
def hitl_db():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(
        engine,
        tables=[
            Organization.__table__,
            Workspace.__table__,
            WorkflowRun.__table__,
            TaskExecution.__table__,
            AuditLog.__table__,
        ],
    )
    SessionClass = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    db = SessionClass()
    org_a = Organization(id=uuid.uuid4(), slug="org-a", name="A")
    org_b = Organization(id=uuid.uuid4(), slug="org-b", name="B")
    db.add_all([org_a, org_b])
    db.commit()
    ws_a = Workspace(id=uuid.uuid4(), org_id=org_a.id, name="A")
    ws_b = Workspace(id=uuid.uuid4(), org_id=org_b.id, name="B")
    db.add_all([ws_a, ws_b])
    db.commit()

    playbook = load_playbook("gated-fixture")
    run_a = start_run(
        db,
        org_id=org_a.id,
        workspace_id=ws_a.id,
        playbook=playbook,
        input_payload={},
        created_by=None,
        principal_snapshot={"role": "owner"},
    )
    alpha = claim(db, "w")
    succeed(db, alpha, {"value": 1})
    gate = claim(db, "w")
    waiting_approval(db, gate, {"draft": "please review"})

    db.org_a_id = org_a.id
    db.org_b_id = org_b.id
    db.run_a_id = run_a.id
    db.SessionClass = SessionClass

    def _get_db():
        inner = SessionClass()
        try:
            yield inner
        finally:
            inner.close()

    app.dependency_overrides[get_db] = _get_db
    try:
        yield db
    finally:
        app.dependency_overrides.pop(get_db, None)
        db.close()


def test_approve_unlocks_downstream(hitl_db: Session):
    db = hitl_db
    token = mint_token(org_id=db.org_a_id, role=Role.SOLUTIONS_ENGINEER)
    resp = client.post(
        f"/workflows/runs/{db.run_a_id}/tasks/gate/approve",
        headers={"Authorization": f"Bearer {token}"},
        json={"edits": {"draft": "edited"}},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    gate = next(t for t in body["tasks"] if t["slug"] == "gate")
    assert gate["status"] == TaskStatus.SUCCEEDED
    assert gate["output_payload"]["draft"] == "edited"

    inner = db.SessionClass()
    try:
        pending = list(
            inner.scalars(
                select(TaskExecution).where(
                    TaskExecution.workflow_run_id == db.run_a_id,
                    TaskExecution.status == TaskStatus.PENDING,
                )
            )
        )
        assert any(t.task_slug == "gamma" for t in pending)
        claimed = claim(inner, "after-approve")
        assert claimed is not None
        assert claimed.task_slug == "gamma"
        audits = list(inner.scalars(select(AuditLog).where(AuditLog.action == "approve")))
        assert len(audits) >= 1
    finally:
        inner.close()


def test_reject_does_not_unlock(hitl_db: Session):
    db = hitl_db
    token = mint_token(org_id=db.org_a_id, role=Role.SOLUTIONS_ENGINEER)
    resp = client.post(
        f"/workflows/runs/{db.run_a_id}/tasks/gate/reject",
        headers={"Authorization": f"Bearer {token}"},
        json={"reason": "nope"},
    )
    assert resp.status_code == 200
    inner = db.SessionClass()
    try:
        claimed = claim(inner, "after-reject")
        assert claimed is None
        run = inner.get(WorkflowRun, db.run_a_id)
        assert run.status == "failed"
    finally:
        inner.close()


def test_viewer_cannot_approve(hitl_db: Session):
    db = hitl_db
    token = mint_token(org_id=db.org_a_id, role=Role.VIEWER)
    resp = client.post(
        f"/workflows/runs/{db.run_a_id}/tasks/gate/approve",
        headers={"Authorization": f"Bearer {token}"},
        json={},
    )
    assert resp.status_code == 403


def test_cross_tenant_approve_is_404(hitl_db: Session):
    db = hitl_db
    token = mint_token(org_id=db.org_b_id, role=Role.ADMIN)
    resp = client.post(
        f"/workflows/runs/{db.run_a_id}/tasks/gate/approve",
        headers={"Authorization": f"Bearer {token}"},
        json={},
    )
    assert resp.status_code == 404


def test_waiting_approval_not_claimed_after_restart(hitl_db: Session):
    claimed = claim(hitl_db, "restarted-worker")
    assert claimed is None
