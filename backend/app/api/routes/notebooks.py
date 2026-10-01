"""4.4 Notebooks: named deals that scope sources, notes, and chat."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from app.core.errors import AppError
from app.db.models import Notebook
from app.db.session import get_db
from app.documents.service import get_or_create_default_workspace
from app.notebooks import service as notebooks
from app.security.audit import record_audit
from app.security.deps import resolve_principal
from app.security.principal import Principal

router = APIRouter(prefix="/notebooks", tags=["notebooks"])


class NotebookIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(..., min_length=1, max_length=120)


class NotebookOut(BaseModel):
    id: str
    name: str
    workspace_id: str
    created_at: str | None = None
    updated_at: str | None = None


class NotebookListOut(BaseModel):
    notebooks: list[NotebookOut]
    total: int
    limit: int
    offset: int


class NotebookSourceOut(BaseModel):
    document_id: str
    title: str | None = None
    filename: str
    enabled: bool
    status: str


class NotebookSourcesIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    document_ids: list[uuid.UUID] = Field(default_factory=list, max_length=500)


def _http(exc: AppError) -> HTTPException:
    return HTTPException(status_code=exc.status_code, detail=exc.message)


def _serialize(notebook: Notebook) -> NotebookOut:
    return NotebookOut(
        id=str(notebook.id),
        name=notebook.name,
        workspace_id=str(notebook.workspace_id),
        created_at=notebook.created_at.isoformat() if notebook.created_at else None,
        updated_at=notebook.updated_at.isoformat() if notebook.updated_at else None,
    )


def _require_writer(principal: Principal) -> None:
    if not principal.can_write_catalog:
        raise HTTPException(status_code=403, detail="You do not have permission to change notebooks.")


@router.get("", response_model=NotebookListOut)
def list_notebooks_endpoint(
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0, le=10000),
    db: Session = Depends(get_db),
    principal: Principal = Depends(resolve_principal),
) -> NotebookListOut:
    workspace = get_or_create_default_workspace(db, principal.org_id)
    rows, total = notebooks.list_notebooks(
        db, org_id=principal.org_id, workspace_id=workspace.id, limit=limit, offset=offset
    )
    return NotebookListOut(
        notebooks=[_serialize(row) for row in rows],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.post("", response_model=NotebookOut, status_code=201)
def create_notebook_endpoint(
    payload: NotebookIn,
    db: Session = Depends(get_db),
    principal: Principal = Depends(resolve_principal),
) -> NotebookOut:
    _require_writer(principal)
    workspace = get_or_create_default_workspace(db, principal.org_id)
    try:
        notebook = notebooks.create_notebook(
            db, org_id=principal.org_id, workspace_id=workspace.id, name=payload.name
        )
    except AppError as exc:
        raise _http(exc) from exc
    record_audit(db, principal, "create", "notebook", str(notebook.id), {"name": notebook.name})
    return _serialize(notebook)


@router.patch("/{notebook_id}", response_model=NotebookOut)
def rename_notebook_endpoint(
    notebook_id: uuid.UUID,
    payload: NotebookIn,
    db: Session = Depends(get_db),
    principal: Principal = Depends(resolve_principal),
) -> NotebookOut:
    _require_writer(principal)
    try:
        notebook = notebooks.rename_notebook(
            db, org_id=principal.org_id, notebook_id=notebook_id, name=payload.name
        )
    except AppError as exc:
        raise _http(exc) from exc
    record_audit(db, principal, "update", "notebook", str(notebook.id), {"name": notebook.name})
    return _serialize(notebook)


@router.delete("/{notebook_id}", status_code=204)
def delete_notebook_endpoint(
    notebook_id: uuid.UUID,
    db: Session = Depends(get_db),
    principal: Principal = Depends(resolve_principal),
) -> None:
    _require_writer(principal)
    try:
        notebooks.delete_notebook(db, org_id=principal.org_id, notebook_id=notebook_id)
    except AppError as exc:
        raise _http(exc) from exc
    record_audit(db, principal, "delete", "notebook", str(notebook_id), None)


@router.get("/{notebook_id}/sources", response_model=list[NotebookSourceOut])
def list_notebook_sources_endpoint(
    notebook_id: uuid.UUID,
    limit: int = Query(100, ge=1, le=100),
    offset: int = Query(0, ge=0, le=10000),
    db: Session = Depends(get_db),
    principal: Principal = Depends(resolve_principal),
) -> list[NotebookSourceOut]:
    try:
        rows = notebooks.source_membership(db, org_id=principal.org_id, notebook_id=notebook_id, limit=limit, offset=offset)
    except AppError as exc:
        raise _http(exc) from exc
    return [
        NotebookSourceOut(
            document_id=str(document.id),
            title=document.title,
            filename=document.original_filename,
            enabled=enabled,
            status=document.status,
        )
        for document, enabled in rows
    ]


@router.put("/{notebook_id}/sources", response_model=list[NotebookSourceOut])
def set_notebook_sources_endpoint(
    notebook_id: uuid.UUID,
    payload: NotebookSourcesIn,
    db: Session = Depends(get_db),
    principal: Principal = Depends(resolve_principal),
) -> list[NotebookSourceOut]:
    _require_writer(principal)
    try:
        rows = notebooks.set_enabled_sources(
            db,
            org_id=principal.org_id,
            notebook_id=notebook_id,
            document_ids=payload.document_ids,
        )
    except AppError as exc:
        raise _http(exc) from exc
    record_audit(
        db,
        principal,
        "update",
        "notebook_sources",
        str(notebook_id),
        {"enabled": len(payload.document_ids)},
    )
    return [
        NotebookSourceOut(
            document_id=str(document.id),
            title=document.title,
            filename=document.original_filename,
            enabled=enabled,
            status=document.status,
        )
        for document, enabled in rows
    ]
