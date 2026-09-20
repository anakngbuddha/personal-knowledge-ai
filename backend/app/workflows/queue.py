"""Durable workflow task queue on PostgreSQL SKIP LOCKED."""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.logging import get_logger
from app.db.models import TaskExecution, TaskStatus, WorkflowRun, WorkflowRunStatus
from app.jobs.backoff import backoff_seconds
from app.workflows.loader import Playbook

logger = get_logger(__name__)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def start_run(
    db: Session,
    *,
    org_id: uuid.UUID,
    workspace_id: uuid.UUID,
    playbook: Playbook,
    input_payload: dict[str, Any] | None,
    created_by: uuid.UUID | None,
    principal_snapshot: dict[str, Any] | None,
) -> WorkflowRun:
    """Materialize every task row before any claim."""
    run = WorkflowRun(
        org_id=org_id,
        workspace_id=workspace_id,
        playbook_slug=playbook.slug,
        status=WorkflowRunStatus.PENDING,
        created_by=created_by,
        principal_snapshot=principal_snapshot,
        input_payload=input_payload or {},
    )
    db.add(run)
    db.flush()
    for task in playbook.tasks:
        db.add(
            TaskExecution(
                workflow_run_id=run.id,
                org_id=org_id,
                task_slug=task.slug,
                depends_on_slugs=list(task.depends_on),
                status=TaskStatus.PENDING,
                input_payload=input_payload or {},
                run_after=_now(),
                max_attempts=settings.workflow_task_max_attempts,
            )
        )
    db.commit()
    db.refresh(run)
    return run


def _deps_satisfied(db: Session, task: TaskExecution) -> bool:
    deps = list(task.depends_on_slugs or [])
    if not deps:
        return True
    rows = list(
        db.scalars(
            select(TaskExecution).where(
                TaskExecution.workflow_run_id == task.workflow_run_id,
                TaskExecution.task_slug.in_(deps),
            )
        )
    )
    if len(rows) != len(deps):
        return False
    return all(row.status == TaskStatus.SUCCEEDED for row in rows)


def claim(db: Session, worker_id: str) -> TaskExecution | None:
    """Atomically claim the next runnable task whose dependencies succeeded."""
    reap_stale(db)
    now = _now()
    candidates = list(
        db.scalars(
            select(TaskExecution)
            .join(WorkflowRun, WorkflowRun.id == TaskExecution.workflow_run_id)
            .where(
                TaskExecution.status == TaskStatus.PENDING,
                TaskExecution.run_after <= now,
                WorkflowRun.status.in_(
                    [
                        WorkflowRunStatus.PENDING,
                        WorkflowRunStatus.RUNNING,
                    ]
                ),
            )
            .order_by(TaskExecution.created_at.asc())
            .limit(50)
            .with_for_update(skip_locked=True)
        )
    )
    for task in candidates:
        if not _deps_satisfied(db, task):
            continue
        task.status = TaskStatus.RUNNING
        task.retry_count += 1
        task.worker_id = worker_id
        task.leased_until = now + timedelta(seconds=settings.workflow_task_stale_seconds)
        task.error_message = None
        run = db.get(WorkflowRun, task.workflow_run_id)
        if run and run.status == WorkflowRunStatus.PENDING:
            run.status = WorkflowRunStatus.RUNNING
        db.commit()
        db.refresh(task)
        return task
    return None


def succeed(db: Session, task: TaskExecution, output: dict[str, Any] | None = None) -> None:
    task.status = TaskStatus.SUCCEEDED
    task.output_payload = output or {}
    task.worker_id = None
    task.leased_until = None
    _refresh_run_status(db, task.workflow_run_id)
    db.commit()


def waiting_approval(db: Session, task: TaskExecution, output: dict[str, Any] | None = None) -> None:
    task.status = TaskStatus.WAITING_APPROVAL
    task.output_payload = output or {}
    task.worker_id = None
    task.leased_until = None
    run = db.get(WorkflowRun, task.workflow_run_id)
    if run:
        run.status = WorkflowRunStatus.WAITING_APPROVAL
    db.commit()


def fail(db: Session, task: TaskExecution, error: str, *, retryable: bool = True) -> None:
    task.worker_id = None
    task.leased_until = None
    task.error_message = error[:4000]
    if not retryable or task.retry_count >= task.max_attempts:
        task.status = TaskStatus.FAILED
        run = db.get(WorkflowRun, task.workflow_run_id)
        if run:
            run.status = WorkflowRunStatus.FAILED
            run.error_message = error[:4000]
        logger.error("task %s dead after %s attempt(s)", task.id, task.retry_count)
    else:
        delay = backoff_seconds(
            task.retry_count,
            base=settings.job_backoff_base_seconds,
            maximum=settings.job_backoff_max_seconds,
            jitter_key=str(task.id),
        )
        task.status = TaskStatus.PENDING
        task.run_after = _now() + timedelta(seconds=delay)
        logger.warning("task %s retrying in %.0fs: %s", task.id, delay, error[:300])
    db.commit()


def reap_stale(db: Session) -> int:
    cutoff = _now()
    result = db.execute(
        update(TaskExecution)
        .where(
            TaskExecution.status == TaskStatus.RUNNING,
            TaskExecution.leased_until.is_not(None),
            TaskExecution.leased_until < cutoff,
        )
        .values(
            status=TaskStatus.PENDING,
            worker_id=None,
            error_message="worker went away; requeued",
            run_after=_now(),
            leased_until=None,
        )
        .execution_options(synchronize_session=False)
    )
    if result.rowcount:
        db.commit()
        logger.warning("requeued %s stale workflow task(s)", result.rowcount)
    return result.rowcount or 0


def heartbeat(db: Session, task: TaskExecution) -> None:
    task.leased_until = _now() + timedelta(seconds=settings.workflow_task_stale_seconds)
    db.commit()


def collect_upstream(db: Session, task: TaskExecution) -> dict[str, Any]:
    deps = list(task.depends_on_slugs or [])
    if not deps:
        return {}
    rows = list(
        db.scalars(
            select(TaskExecution).where(
                TaskExecution.workflow_run_id == task.workflow_run_id,
                TaskExecution.task_slug.in_(deps),
            )
        )
    )
    return {row.task_slug: (row.output_payload or {}) for row in rows}


def _refresh_run_status(db: Session, run_id: uuid.UUID) -> None:
    run = db.get(WorkflowRun, run_id)
    if run is None:
        return
    tasks = list(
        db.scalars(select(TaskExecution).where(TaskExecution.workflow_run_id == run_id))
    )
    if any(t.status == TaskStatus.FAILED for t in tasks):
        run.status = WorkflowRunStatus.FAILED
        return
    if any(t.status == TaskStatus.WAITING_APPROVAL for t in tasks):
        run.status = WorkflowRunStatus.WAITING_APPROVAL
        return
    if tasks and all(t.status == TaskStatus.SUCCEEDED for t in tasks):
        run.status = WorkflowRunStatus.SUCCEEDED
        return
    run.status = WorkflowRunStatus.RUNNING
