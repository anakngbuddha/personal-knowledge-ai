"""Workflow run inspection and HITL approve/reject endpoints."""

from __future__ import annotations

import re
import uuid
from pathlib import PurePosixPath
from typing import Any

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from fastapi.responses import Response
from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.core.config import settings
from app.core.errors import GenerationRateLimited, TokenBudgetExhausted
from app.db.models import TaskExecution, TaskStatus, WorkflowRun, WorkflowRunStatus
from app.db.session import get_db
from app.documents.service import get_or_create_default_workspace
from app.security.audit import record_audit
from app.security.deps import resolve_principal
from app.security.principal import Principal
from app.workflows import queue
from app.workflows.loader import RUNNABLE_PLAYBOOKS, list_playbooks, load_playbook
from app.workflows.schemas import (
    PlaybookListOut,
    PlaybookOut,
    TaskApproveIn,
    TaskCounts,
    TaskOut,
    TaskRejectIn,
    WorkflowRunListOut,
    WorkflowRunOut,
    WorkflowRunSummaryOut,
)

router = APIRouter(tags=["workflows"])

_UNSAFE_FILENAME = re.compile(r'["\'\r\n\\/;:\*\?<>\|]')
_TASK_COUNT_KEYS = (
    TaskStatus.PENDING,
    TaskStatus.RUNNING,
    TaskStatus.WAITING_APPROVAL,
    TaskStatus.SUCCEEDED,
    TaskStatus.FAILED,
)


def _require_approver(principal: Principal) -> None:
    if not principal.can_write_catalog:
        raise HTTPException(status_code=403, detail="solutions engineer role required")


def _get_run(db: Session, run_id: uuid.UUID, org_id: uuid.UUID) -> WorkflowRun | None:
    return db.scalars(
        select(WorkflowRun)
        .options(selectinload(WorkflowRun.tasks))
        .where(WorkflowRun.id == run_id, WorkflowRun.org_id == org_id)
    ).first()


def _payload_summary(payload: dict[str, Any] | None) -> str:
    if not payload:
        return ""
    parts: list[str] = []
    if "row_count" in payload:
        parts.append(f"row_count={payload['row_count']}")
    if "needs_review" in payload:
        parts.append(f"needs_review={payload['needs_review']}")
    answers = payload.get("answers")
    if isinstance(answers, list):
        parts.append(f"answers={len(answers)}")
    requirements = payload.get("requirements")
    if isinstance(requirements, list):
        parts.append(f"requirements={len(requirements)}")
    return ", ".join(parts)


def _log_line(task: TaskExecution) -> str:
    bits = [task.status]
    summary = _payload_summary(task.output_payload if isinstance(task.output_payload, dict) else None)
    if summary:
        bits.append(summary)
    if task.retry_count:
        bits.append(f"retries={task.retry_count}")
    if task.error_message:
        bits.append(task.error_message[:200])
    return " · ".join(bits)


def _task_out(task: TaskExecution) -> TaskOut:
    updated = task.updated_at.isoformat() if task.updated_at else None
    return TaskOut(
        id=str(task.id),
        slug=task.task_slug,
        status=task.status,
        depends_on_slugs=list(task.depends_on_slugs or []),
        output_payload=task.output_payload,
        error_message=task.error_message,
        retry_count=task.retry_count,
        max_attempts=task.max_attempts,
        worker_id=task.worker_id,
        updated_at=updated,
        log_line=_log_line(task),
    )


def _task_counts(tasks: list[TaskExecution]) -> TaskCounts:
    counts = {key: 0 for key in _TASK_COUNT_KEYS}
    for task in tasks:
        if task.status in counts:
            counts[task.status] += 1
    return TaskCounts(**counts)


def _run_out(run: WorkflowRun) -> WorkflowRunOut:
    tasks = sorted(run.tasks, key=lambda t: t.created_at)
    return WorkflowRunOut(
        id=str(run.id),
        playbook_slug=run.playbook_slug,
        status=run.status,
        org_id=str(run.org_id),
        workspace_id=str(run.workspace_id),
        input_payload=run.input_payload,
        error_message=run.error_message,
        tasks=[_task_out(t) for t in tasks],
        created_at=run.created_at.isoformat(),
        updated_at=run.updated_at.isoformat(),
    )


def _run_summary(run: WorkflowRun) -> WorkflowRunSummaryOut:
    return WorkflowRunSummaryOut(
        id=str(run.id),
        playbook_slug=run.playbook_slug,
        status=run.status,
        created_at=run.created_at.isoformat(),
        updated_at=run.updated_at.isoformat(),
        error_message=run.error_message,
        task_counts=_task_counts(list(run.tasks)),
    )


def _apply_approve_edits(merged: dict[str, Any], payload: TaskApproveIn | None) -> dict[str, Any]:
    edits = (payload.edits if payload else {}) or {}
    merged.update(edits)
    if payload is None or not payload.answers:
        return merged
    existing = list(merged.get("answers") or [])
    by_id = {str(row.get("id")): idx for idx, row in enumerate(existing) if isinstance(row, dict) and row.get("id")}
    for edit in payload.answers:
        idx = by_id.get(edit.id)
        if idx is None:
            continue
        row = dict(existing[idx])
        if edit.response is not None:
            row["response"] = edit.response
        if edit.status is not None:
            row["status"] = edit.status
        existing[idx] = row
    merged["answers"] = existing
    merged["needs_review"] = False
    return merged


def safe_download_filename(name: str, default: str = "rfp-response.docx") -> str:
    base = PurePosixPath(str(name or "").replace("\\", "/")).name
    cleaned = _UNSAFE_FILENAME.sub("", base).strip()
    if not cleaned or cleaned in {".", ".."}:
        return default
    if len(cleaned) > 180:
        stem, dot, suffix = cleaned.rpartition(".")
        if dot:
            cleaned = f"{stem[:160]}.{suffix[:19]}"
        else:
            cleaned = cleaned[:180]
    return cleaned


@router.get("/playbooks", response_model=PlaybookListOut)
def get_playbooks(
    principal: Principal = Depends(resolve_principal),
) -> PlaybookListOut:
    _ = principal  # tenant-authenticated catalog of YAML playbooks (not tenant-scoped files)
    items = [
        PlaybookOut(
            slug=playbook.slug,
            name=playbook.name,
            version=playbook.version,
            task_count=len(playbook.tasks),
            runnable=playbook.slug in RUNNABLE_PLAYBOOKS,
        )
        for playbook in list_playbooks()
    ]
    items.sort(key=lambda item: item.name.lower())
    return PlaybookListOut(playbooks=items)


@router.get("/workflows/runs", response_model=WorkflowRunListOut)
def list_runs(
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
    principal: Principal = Depends(resolve_principal),
) -> WorkflowRunListOut:
    total = db.scalar(
        select(func.count()).select_from(WorkflowRun).where(WorkflowRun.org_id == principal.org_id)
    ) or 0
    runs = list(
        db.scalars(
            select(WorkflowRun)
            .options(selectinload(WorkflowRun.tasks))
            .where(WorkflowRun.org_id == principal.org_id)
            .order_by(WorkflowRun.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
    )
    return WorkflowRunListOut(
        runs=[_run_summary(r) for r in runs],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get("/workflows/runs/{run_id}", response_model=WorkflowRunOut)
def get_run(
    run_id: uuid.UUID,
    db: Session = Depends(get_db),
    principal: Principal = Depends(resolve_principal),
) -> WorkflowRunOut:
    run = _get_run(db, run_id, principal.org_id)
    if run is None:
        raise HTTPException(status_code=404, detail="Workflow run not found")
    return _run_out(run)


@router.post("/workflows/runs/{run_id}/tasks/{task_slug}/approve", response_model=WorkflowRunOut)
def approve_task(
    run_id: uuid.UUID,
    task_slug: str,
    payload: TaskApproveIn | None = None,
    db: Session = Depends(get_db),
    principal: Principal = Depends(resolve_principal),
) -> WorkflowRunOut:
    _require_approver(principal)
    run = _get_run(db, run_id, principal.org_id)
    if run is None:
        raise HTTPException(status_code=404, detail="Workflow run not found")
    task = next((t for t in run.tasks if t.task_slug == task_slug), None)
    if task is None or task.status != TaskStatus.WAITING_APPROVAL:
        raise HTTPException(status_code=404, detail="Task not found")
    merged = _apply_approve_edits(dict(task.output_payload or {}), payload)
    edits = (payload.edits if payload else {}) or {}
    task.output_payload = merged
    task.status = TaskStatus.SUCCEEDED
    task.error_message = None
    if run.status == WorkflowRunStatus.WAITING_APPROVAL:
        run.status = WorkflowRunStatus.RUNNING
    record_audit(
        db,
        principal,
        action="approve",
        resource_type="workflow_task",
        resource_id=str(task.id),
        details={
            "run_id": str(run.id),
            "task_slug": task_slug,
            "edits": edits,
            "answer_ids": [a.id for a in (payload.answers or [])] if payload else [],
        },
    )
    queue._refresh_run_status(db, run.id)
    db.commit()
    db.refresh(run)
    return _run_out(_get_run(db, run.id, principal.org_id) or run)


@router.post("/workflows/runs/{run_id}/tasks/{task_slug}/reject", response_model=WorkflowRunOut)
def reject_task(
    run_id: uuid.UUID,
    task_slug: str,
    payload: TaskRejectIn | None = None,
    db: Session = Depends(get_db),
    principal: Principal = Depends(resolve_principal),
) -> WorkflowRunOut:
    _require_approver(principal)
    run = _get_run(db, run_id, principal.org_id)
    if run is None:
        raise HTTPException(status_code=404, detail="Workflow run not found")
    task = next((t for t in run.tasks if t.task_slug == task_slug), None)
    if task is None or task.status != TaskStatus.WAITING_APPROVAL:
        raise HTTPException(status_code=404, detail="Task not found")
    reason = (payload.reason if payload else "") or "rejected"
    task.status = TaskStatus.FAILED
    task.error_message = reason[:4000]
    run.status = WorkflowRunStatus.FAILED
    run.error_message = reason[:4000]
    record_audit(
        db,
        principal,
        action="reject",
        resource_type="workflow_task",
        resource_id=str(task.id),
        details={"run_id": str(run.id), "task_slug": task_slug, "reason": reason},
    )
    db.commit()
    db.refresh(run)
    return _run_out(_get_run(db, run.id, principal.org_id) or run)


def start_playbook_run(
    db: Session,
    principal: Principal,
    playbook_slug: str,
    input_payload: dict[str, Any],
) -> WorkflowRun:
    workspace = get_or_create_default_workspace(db, principal.org_id)
    playbook = load_playbook(playbook_slug)
    snapshot = principal.describe()
    return queue.start_run(
        db,
        org_id=principal.org_id,
        workspace_id=workspace.id,
        playbook=playbook,
        input_payload=input_payload,
        created_by=principal.user_id,
        principal_snapshot=snapshot,
    )


@router.post("/workflows/rfp/run", response_model=WorkflowRunOut)
async def start_rfp_run(
    file: UploadFile = File(...),
    account_ref: str | None = Form(default=None),
    db: Session = Depends(get_db),
    principal: Principal = Depends(resolve_principal),
) -> WorkflowRunOut:
    """Upload a customer RFP spreadsheet and materialize the responder playbook."""
    _require_approver(principal)
    from app.generation.rate_limit import check_rate_limit, check_token_budget
    from app.storage.factory import get_storage

    try:
        check_rate_limit(principal.user_id)
        check_token_budget(db, principal.org_id)
    except (GenerationRateLimited, TokenBudgetExhausted) as exc:
        raise HTTPException(status_code=429, detail=str(exc)) from exc

    data = await file.read()
    if len(data) > settings.max_upload_bytes:
        raise HTTPException(status_code=413, detail="RFP file exceeds upload limit")
    filename = file.filename or "rfp.xlsx"
    lowered = filename.lower()
    if not (lowered.endswith(".xlsx") or lowered.endswith(".csv") or data[:2] == b"PK"):
        # Allow CSV by content even without extension.
        sample = data[:200].decode("utf-8", errors="replace")
        if "," not in sample and "\t" not in sample:
            raise HTTPException(status_code=400, detail="RFP must be .xlsx or .csv")

    ext = ".csv" if lowered.endswith(".csv") else ".xlsx"
    storage_key = f"rfp/{principal.org_id}/{uuid.uuid4()}/source{ext}"
    get_storage().put(storage_key, data)
    run = start_playbook_run(
        db,
        principal,
        "rfp-response",
        {
            "storage_key": storage_key,
            "filename": filename,
            "account_ref": account_ref,
        },
    )
    return _run_out(_get_run(db, run.id, principal.org_id) or run)


@router.get("/workflows/runs/{run_id}/deliverable")
def download_deliverable(
    run_id: uuid.UUID,
    db: Session = Depends(get_db),
    principal: Principal = Depends(resolve_principal),
) -> Response:
    run = _get_run(db, run_id, principal.org_id)
    if run is None:
        raise HTTPException(status_code=404, detail="Workflow run not found")
    export = next((t for t in run.tasks if t.task_slug == "export_deliverable"), None)
    if export is None or export.status != TaskStatus.SUCCEEDED:
        raise HTTPException(status_code=404, detail="Deliverable not ready")
    key = (export.output_payload or {}).get("storage_key")
    raw_name = (export.output_payload or {}).get("filename") or "rfp-response.docx"
    filename = safe_download_filename(str(raw_name))
    if not key:
        raise HTTPException(status_code=404, detail="Deliverable not ready")
    from app.storage.factory import get_storage

    data = get_storage().get(key)
    return Response(
        content=data,
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
