"""Phase 10 tribal notes API."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from app.core.errors import AppError
from app.db.models import Note
from app.db.session import get_db
from app.documents.service import get_or_create_default_workspace
from app.notes import service as notes
from app.security.audit import record_audit
from app.security.deps import resolve_principal
from app.security.principal import Principal

router = APIRouter(prefix="/notes", tags=["notes"])


class NoteLinkOut(BaseModel):
    target_kind: str
    target_ref: str
    display_text: str | None = None
    resolved: bool
    resolved_id: str | None = None


class NoteOut(BaseModel):
    id: str
    title: str
    slug: str
    body: str
    workspace_id: str
    created_by: str | None = None
    created_at: str | None = None
    updated_at: str | None = None
    links: list[NoteLinkOut] = Field(default_factory=list)


class NoteListOut(BaseModel):
    notes: list[NoteOut]
    total: int
    limit: int
    offset: int


class NoteIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str = Field(..., min_length=1, max_length=512)
    body: str = Field("", max_length=200_000)
    slug: str | None = Field(None, max_length=128)


class NoteUpdateIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str | None = Field(None, min_length=1, max_length=512)
    body: str | None = Field(None, max_length=200_000)


def _http(exc: AppError) -> HTTPException:
    return HTTPException(status_code=exc.status_code, detail=exc.message)


def _serialize(note: Note) -> NoteOut:
    return NoteOut(
        id=str(note.id),
        title=note.title,
        slug=note.slug,
        body=note.body,
        workspace_id=str(note.workspace_id),
        created_by=str(note.created_by) if note.created_by else None,
        created_at=note.created_at.isoformat() if note.created_at else None,
        updated_at=note.updated_at.isoformat() if note.updated_at else None,
        links=[
            NoteLinkOut(
                target_kind=link.target_kind,
                target_ref=link.target_ref,
                display_text=link.display_text,
                resolved=link.resolved,
                resolved_id=str(link.resolved_id) if link.resolved_id else None,
            )
            for link in note.links
        ],
    )


@router.get("", response_model=NoteListOut)
def list_notes(
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    search: str | None = Query(None, max_length=200),
    db: Session = Depends(get_db),
    principal: Principal = Depends(resolve_principal),
) -> NoteListOut:
    workspace = get_or_create_default_workspace(db, principal.org_id)
    rows, total = notes.list_notes(
        db,
        org_id=principal.org_id,
        workspace_id=workspace.id,
        limit=limit,
        offset=offset,
        search=search,
    )
    return NoteListOut(
        notes=[_serialize(row) for row in rows],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.post("", response_model=NoteOut, status_code=201)
def create_note(
    payload: NoteIn,
    db: Session = Depends(get_db),
    principal: Principal = Depends(resolve_principal),
) -> NoteOut:
    if not principal.can_write_catalog:
        raise HTTPException(status_code=403, detail="solutions engineer role required")
    workspace = get_or_create_default_workspace(db, principal.org_id)
    try:
        note = notes.create_note(
            db,
            org_id=principal.org_id,
            workspace_id=workspace.id,
            title=payload.title,
            body=payload.body,
            slug=payload.slug,
            created_by=principal.user_id,
        )
    except AppError as exc:
        raise _http(exc) from exc
    record_audit(db, principal, "create", "note", str(note.id), {"slug": note.slug})
    return _serialize(note)


@router.get("/by-link/{kind}/{ref}", response_model=NoteListOut)
def notes_linking_to(
    kind: str,
    ref: str,
    db: Session = Depends(get_db),
    principal: Principal = Depends(resolve_principal),
) -> NoteListOut:
    rows = notes.backlinks(db, org_id=principal.org_id, kind=kind, target_ref=ref)
    return NoteListOut(
        notes=[_serialize(row) for row in rows],
        total=len(rows),
        limit=len(rows),
        offset=0,
    )


@router.get("/{note_id}", response_model=NoteOut)
def get_note(
    note_id: uuid.UUID,
    db: Session = Depends(get_db),
    principal: Principal = Depends(resolve_principal),
) -> NoteOut:
    try:
        note = notes.get_note(db, org_id=principal.org_id, note_id=note_id)
    except AppError as exc:
        raise _http(exc) from exc
    return _serialize(note)


@router.put("/{note_id}", response_model=NoteOut)
def update_note(
    note_id: uuid.UUID,
    payload: NoteUpdateIn,
    db: Session = Depends(get_db),
    principal: Principal = Depends(resolve_principal),
) -> NoteOut:
    if not principal.can_write_catalog:
        raise HTTPException(status_code=403, detail="solutions engineer role required")
    try:
        note = notes.update_note(
            db,
            org_id=principal.org_id,
            note_id=note_id,
            title=payload.title,
            body=payload.body,
        )
    except AppError as exc:
        raise _http(exc) from exc
    record_audit(db, principal, "update", "note", str(note.id), {"slug": note.slug})
    return _serialize(note)


@router.delete("/{note_id}", status_code=204)
def delete_note(
    note_id: uuid.UUID,
    db: Session = Depends(get_db),
    principal: Principal = Depends(resolve_principal),
) -> None:
    if not principal.can_write_catalog:
        raise HTTPException(status_code=403, detail="solutions engineer role required")
    try:
        notes.delete_note(db, org_id=principal.org_id, note_id=note_id)
    except AppError as exc:
        raise _http(exc) from exc
    record_audit(db, principal, "delete", "note", str(note_id))

