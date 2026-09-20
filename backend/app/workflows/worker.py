"""Sequential in-process worker for workflow tasks."""

from __future__ import annotations

import os
import socket
import threading
import time

from app.core.config import settings
from app.core.logging import get_logger
from app.db.models import TaskStatus, WorkflowRun
from app.db.session import SessionLocal
from app.security.labels import Role
from app.security.principal import Principal, owner_principal
from app.workflows import queue
from app.workflows.handlers import HandlerContext, get_handler
from app.workflows.loader import load_playbook

logger = get_logger(__name__)

_stop = threading.Event()
_threads: list[threading.Thread] = []


def worker_id(index: int = 0) -> str:
    return f"{socket.gethostname()}:{os.getpid()}:wf-{index}"


def _principal_from_run(run: WorkflowRun) -> Principal:
    snap = run.principal_snapshot or {}
    org_id = run.org_id
    user_id = run.created_by
    role = snap.get("role") or Role.OWNER
    if role in (Role.OWNER, Role.ADMIN, "owner", "admin"):
        return owner_principal(org_id, user_id)
    return Principal(
        org_id=org_id,
        user_id=user_id,
        role=str(role),
        max_sensitivity=str(snap.get("max_sensitivity") or "internal"),
        allow_vendor_restricted=bool(snap.get("allow_vendor_restricted")),
        account_refs=None if snap.get("sees_all_accounts") else frozenset(snap.get("accounts") or []),
        include_unapproved=True,
        label="workflow",
    )


def run_once(identity: str) -> bool:
    db = SessionLocal()
    try:
        task = queue.claim(db, identity)
        if task is None:
            return False
        run = db.get(WorkflowRun, task.workflow_run_id)
        if run is None:
            queue.fail(db, task, "workflow run missing", retryable=False)
            return True
        try:
            playbook = load_playbook(run.playbook_slug)
            spec = playbook.task_by_slug(task.task_slug)
            handler = get_handler(spec.handler)
            upstream = queue.collect_upstream(db, task)
            payload = dict(task.input_payload or {})
            payload["upstream"] = upstream
            ctx = HandlerContext(
                db=db,
                run=run,
                task=task,
                principal=_principal_from_run(run),
                upstream=upstream,
            )
            output = handler(ctx, payload)
            if spec.gate == "human_approval":
                queue.waiting_approval(db, task, output)
            else:
                queue.succeed(db, task, output)
        except Exception as exc:  # noqa: BLE001
            logger.exception("workflow task %s failed", task.id)
            queue.fail(db, task, f"{type(exc).__name__}: {exc}", retryable=True)
        return True
    finally:
        db.close()


def loop(index: int = 0) -> None:
    identity = worker_id(index)
    logger.info("workflow worker %s started", identity)
    while not _stop.is_set():
        try:
            did_work = run_once(identity)
        except Exception:  # noqa: BLE001
            logger.exception("workflow worker %s: unexpected error", identity)
            did_work = False
        if not did_work:
            _stop.wait(settings.worker_poll_seconds)
    logger.info("workflow worker %s stopped", identity)


def start_workflow_workers() -> None:
    if not settings.workflow_worker_enabled:
        logger.warning("workflow worker disabled")
        return
    if _threads:
        return
    for index in range(max(1, settings.workflow_worker_concurrency)):
        thread = threading.Thread(target=loop, args=(index,), daemon=True, name=f"workflow-{index}")
        thread.start()
        _threads.append(thread)


def stop_workflow_workers(timeout: float = 5.0) -> None:
    _stop.set()
    deadline = time.monotonic() + timeout
    for thread in _threads:
        thread.join(max(0.0, deadline - time.monotonic()))
    _threads.clear()
    _stop.clear()
