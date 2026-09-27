"""Explicit confirmation for consequential actions proposed in Ask Intelligence."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import AgentAction, Note, Product, TaskExecution, TaskStatus, WorkflowRun
from app.db.session import get_db
from app.notes import service as notes
from app.security.audit import record_audit
from app.security.deps import resolve_principal
from app.security.principal import MCP_WRITE_SCOPE, Principal

router = APIRouter(prefix="/agent/actions", tags=["agent-actions"])


class ActionOut(BaseModel):
    id: str
    kind: str
    status: str
    result: dict | None = None


def _action(db: Session, principal: Principal, action_id: uuid.UUID) -> AgentAction:
    action = db.scalar(select(AgentAction).where(AgentAction.id == action_id,
        AgentAction.org_id == principal.org_id, AgentAction.user_id == principal.user_id).with_for_update())
    if action is None:
        raise HTTPException(status_code=404, detail="Action not found")
    return action


@router.post("/{action_id}/confirm", response_model=ActionOut)
def confirm_action(action_id: uuid.UUID, db: Session = Depends(get_db),
                   principal: Principal = Depends(resolve_principal)) -> ActionOut:
    action = _action(db, principal, action_id)
    if action.status not in ("pending", "executing"):
        return ActionOut(id=str(action.id), kind=action.kind, status=action.status, result=action.result)
    expiry = action.expires_at.replace(tzinfo=action.expires_at.tzinfo or timezone.utc)
    if expiry < datetime.now(timezone.utc):
        action.status = "expired"
        db.commit()
        raise HTTPException(status_code=410, detail="Approval expired")
    if not principal.can_write_catalog or not principal.has_scope(MCP_WRITE_SCOPE):
        raise HTTPException(status_code=403, detail="Write permission required")
    if action.kind == "delete_note":
        note_id = uuid.UUID(action.arguments["note_id"])
        note = db.scalar(select(Note).where(Note.id == note_id, Note.org_id == principal.org_id,
                                            Note.workspace_id == action.workspace_id))
        if note is None and action.status == "pending":
            raise HTTPException(status_code=404, detail="Note not found")
        if note is not None:
            action.status = "executing"
            db.commit()
            notes.delete_note(db, org_id=principal.org_id, note_id=note_id)
        result = {"deleted_note_id": str(note_id)}
    elif action.kind == "publish_product":
        from app.catalog.models import ProductIn
        from app.catalog.service import CatalogService
        data = ProductIn.model_validate(action.arguments)
        existing = db.scalar(select(Product).where(Product.org_id == principal.org_id,
            Product.workspace_id == action.workspace_id, Product.name == data.name,
            Product.vendor == data.vendor)) if action.status == "executing" else None
        if existing is None:
            action.status = "executing"
            db.commit()
            existing = CatalogService(db).create_product(principal.org_id, action.workspace_id, data)
        result = {"product_id": str(existing.id), "name": existing.name}
    elif action.kind == "approve_workflow_task":
        from app.api.routes.workflows import approve_task
        run_id = uuid.UUID(action.arguments["run_id"])
        task_slug = action.arguments["task_slug"]
        run = db.scalar(select(WorkflowRun).where(WorkflowRun.id == run_id,
            WorkflowRun.org_id == principal.org_id, WorkflowRun.workspace_id == action.workspace_id))
        if run is None:
            raise HTTPException(status_code=404, detail="Workflow run not found")
        task = db.scalar(select(TaskExecution).where(TaskExecution.workflow_run_id == run.id,
            TaskExecution.task_slug == task_slug))
        if task is None or task.status not in (TaskStatus.WAITING_APPROVAL, TaskStatus.SUCCEEDED):
            raise HTTPException(status_code=409, detail="Workflow task cannot be approved")
        if task.status == TaskStatus.WAITING_APPROVAL:
            action.status = "executing"
            db.commit()
            approve_task(run_id, task_slug, db=db, principal=principal)
        result = {"run_id": str(run_id), "task_slug": task_slug}
    else:
        raise HTTPException(status_code=400, detail="Unsupported action")
    action.status = "confirmed"
    action.result = result
    action.resolved_at = datetime.now(timezone.utc)
    db.commit()
    record_audit(db, principal, "agent_confirm", action.kind, str(action.id), result)
    return ActionOut(id=str(action.id), kind=action.kind, status=action.status, result=result)


@router.post("/{action_id}/reject", response_model=ActionOut)
def reject_action(action_id: uuid.UUID, db: Session = Depends(get_db),
                  principal: Principal = Depends(resolve_principal)) -> ActionOut:
    action = _action(db, principal, action_id)
    if action.status == "pending":
        action.status = "rejected"
        action.resolved_at = datetime.now(timezone.utc)
        db.commit()
        record_audit(db, principal, "agent_reject", action.kind, str(action.id))
    return ActionOut(id=str(action.id), kind=action.kind, status=action.status, result=action.result)
