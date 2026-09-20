"""Durable workflow queue: materialization, dependencies, crash recovery."""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import create_engine, select
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.models import (
    Base,
    Organization,
    TaskExecution,
    TaskStatus,
    WorkflowRun,
    WorkflowRunStatus,
    Workspace,
)
from app.workflows.handlers import get_handler  # noqa: F401 - register fixtures
from app.workflows.loader import load_playbook, parse_playbook
from app.workflows.queue import claim, fail, reap_stale, start_run, succeed, waiting_approval
from app.workflows.worker import run_once


@compiles(JSONB, "sqlite")
def _compile_jsonb_sqlite(element, compiler, **kw):
    return "JSON"


def _session():
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
        ],
    )
    SessionClass = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    db = SessionClass()
    org = Organization(id=uuid.uuid4(), slug="acme", name="Acme")
    db.add(org)
    db.commit()
    ws = Workspace(id=uuid.uuid4(), org_id=org.id, name="Default")
    db.add(ws)
    db.commit()
    db.org_id = org.id
    db.workspace_id = ws.id
    return db


def test_playbook_cycle_is_rejected():
    try:
        parse_playbook(
            {
                "slug": "cycle",
                "tasks": [
                    {"slug": "a", "handler": "fixture.alpha", "depends_on": ["b"]},
                    {"slug": "b", "handler": "fixture.beta", "depends_on": ["a"]},
                ],
            }
        )
        assert False, "expected cycle error"
    except Exception as exc:
        assert "cycle" in str(exc).lower() or "depends_on" in str(exc).lower()


def test_materialize_three_tasks_only_alpha_claimable():
    db = _session()
    playbook = load_playbook("linear-fixture")
    run = start_run(
        db,
        org_id=db.org_id,
        workspace_id=db.workspace_id,
        playbook=playbook,
        input_payload={"n": 1},
        created_by=None,
        principal_snapshot={"role": "owner"},
    )
    tasks = list(
        db.scalars(select(TaskExecution).where(TaskExecution.workflow_run_id == run.id))
    )
    assert len(tasks) == 3
    first = claim(db, "w1")
    assert first is not None
    assert first.task_slug == "alpha"
    second = claim(db, "w2")
    assert second is None  # beta blocked until alpha succeeds


def test_succeed_unlocks_downstream():
    db = _session()
    playbook = load_playbook("linear-fixture")
    start_run(
        db,
        org_id=db.org_id,
        workspace_id=db.workspace_id,
        playbook=playbook,
        input_payload={},
        created_by=None,
        principal_snapshot={},
    )
    alpha = claim(db, "w1")
    succeed(db, alpha, {"value": 1})
    beta = claim(db, "w1")
    assert beta is not None
    assert beta.task_slug == "beta"


def test_waiting_approval_blocks_downstream():
    db = _session()
    playbook = load_playbook("gated-fixture")
    start_run(
        db,
        org_id=db.org_id,
        workspace_id=db.workspace_id,
        playbook=playbook,
        input_payload={},
        created_by=None,
        principal_snapshot={},
    )
    alpha = claim(db, "w1")
    succeed(db, alpha, {"value": 1})
    gate = claim(db, "w1")
    assert gate.task_slug == "gate"
    waiting_approval(db, gate, {"draft": True})
    blocked = claim(db, "w1")
    assert blocked is None


def test_stale_running_task_is_requeued():
    db = _session()
    playbook = load_playbook("linear-fixture")
    start_run(
        db,
        org_id=db.org_id,
        workspace_id=db.workspace_id,
        playbook=playbook,
        input_payload={},
        created_by=None,
        principal_snapshot={},
    )
    alpha = claim(db, "w1")
    alpha.leased_until = datetime.now(timezone.utc) - timedelta(seconds=10)
    db.commit()
    reaped = reap_stale(db)
    assert reaped == 1
    again = claim(db, "w2")
    assert again is not None
    assert again.task_slug == "alpha"
    succeed(db, again, {"value": 1})
    beta = claim(db, "w2")
    assert beta.task_slug == "beta"


def test_linear_run_completes_via_worker():
    db = _session()
    playbook = load_playbook("linear-fixture")
    run = start_run(
        db,
        org_id=db.org_id,
        workspace_id=db.workspace_id,
        playbook=playbook,
        input_payload={},
        created_by=None,
        principal_snapshot={"role": "owner", "sees_all_accounts": True},
    )
    # Drive the in-process worker against this sqlite session by claiming here
    # then executing handlers the same way the worker does.
    from app.workflows.handlers import HandlerContext, get_handler
    from app.workflows.queue import collect_upstream
    from app.security.principal import owner_principal

    for _ in range(3):
        task = claim(db, "test-worker")
        assert task is not None
        spec = playbook.task_by_slug(task.task_slug)
        handler = get_handler(spec.handler)
        upstream = collect_upstream(db, task)
        ctx = HandlerContext(
            db=db,
            run=db.get(WorkflowRun, run.id),
            task=task,
            principal=owner_principal(db.org_id),
            upstream=upstream,
        )
        output = handler(ctx, {"upstream": upstream})
        succeed(db, task, output)

    run = db.get(WorkflowRun, run.id)
    assert run.status == WorkflowRunStatus.SUCCEEDED
    gamma = db.scalars(
        select(TaskExecution).where(
            TaskExecution.workflow_run_id == run.id,
            TaskExecution.task_slug == "gamma",
        )
    ).first()
    assert gamma.output_payload["value"] == 3


def test_skip_locked_does_not_double_claim_same_row():
    """SQLite approximation: a claimed running task is not pending."""
    db = _session()
    playbook = load_playbook("linear-fixture")
    start_run(
        db,
        org_id=db.org_id,
        workspace_id=db.workspace_id,
        playbook=playbook,
        input_payload={},
        created_by=None,
        principal_snapshot={},
    )
    first = claim(db, "w1")
    second = claim(db, "w2")
    assert first is not None
    assert first.status == TaskStatus.RUNNING
    assert second is None or second.id != first.id
