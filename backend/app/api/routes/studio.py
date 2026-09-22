"""4.5 Briefing, FAQ, compare, and suggested questions."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from app.core.errors import AppError
from app.db.models import Document
from app.db.session import get_db
from app.documents.service import get_or_create_default_workspace
from app.security.audit import record_audit
from app.security.deps import resolve_principal
from app.security.principal import Principal
from app.studio.service import suggested_questions, run_studio

router = APIRouter(prefix="/studio", tags=["studio"])


class StudioIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: str = Field(..., pattern="^(briefing|faq|compare)$")
    document_ids: list[uuid.UUID] = Field(default_factory=list, max_length=12)
    notebook_id: uuid.UUID | None = None
    save_as_note: bool = False


class StudioOut(BaseModel):
    markdown: str
    source_titles: list[str]
    note_id: str | None = None


class QuestionsOut(BaseModel):
    document_id: str
    questions: list[str]


def _http(exc: AppError) -> HTTPException:
    return HTTPException(status_code=exc.status_code, detail=exc.message)


@router.get("/questions", response_model=QuestionsOut)
def questions_endpoint(
    document_id: uuid.UUID = Query(...),
    db: Session = Depends(get_db),
    principal: Principal = Depends(resolve_principal),
) -> QuestionsOut:
    document = db.get(Document, document_id)
    if document is None or document.org_id != principal.org_id:
        raise HTTPException(status_code=404, detail="That source was not found.")
    try:
        questions = suggested_questions(db, document)
    except AppError as exc:
        raise _http(exc) from exc
    return QuestionsOut(document_id=str(document.id), questions=questions)


@router.post("/run", response_model=StudioOut)
def run_endpoint(
    payload: StudioIn,
    db: Session = Depends(get_db),
    principal: Principal = Depends(resolve_principal),
) -> StudioOut:
    workspace = get_or_create_default_workspace(db, principal.org_id)
    if payload.save_as_note and not principal.can_write_catalog:
        raise HTTPException(status_code=403, detail="You do not have permission to save notes.")
    try:
        result = run_studio(
            db,
            org_id=principal.org_id,
            workspace_id=workspace.id,
            kind=payload.kind,
            document_ids=payload.document_ids,
            notebook_id=payload.notebook_id,
            save_as_note=payload.save_as_note,
            created_by=principal.user_id,
        )
    except AppError as exc:
        raise _http(exc) from exc
    record_audit(
        db,
        principal,
        "run",
        "studio",
        result.get("note_id"),
        {"kind": payload.kind, "sources": len(payload.document_ids)},
    )
    return StudioOut(**result)
