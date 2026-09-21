"""4.1 Customer brief API.

One endpoint, because the flow is one action: the user pastes what the customer sent,
and gets back a brief they can read, correct, and keep. Saving it as a note is the
default, so the brief is searchable and editable in Notes like anything else written by
hand, and so the rest of the conversation can retrieve it.

Editing a brief is editing its note. There is deliberately no second write path here.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from app.advisor.brief import extract_customer_brief, save_brief_as_note
from app.core.errors import AppError
from app.db.session import get_db
from app.documents.service import get_or_create_default_workspace
from app.security.audit import record_audit
from app.security.deps import resolve_principal
from app.security.principal import Principal

router = APIRouter(prefix="/advisor", tags=["advisor"])


class BriefIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    requirements: str = Field(..., min_length=1, max_length=200_000)
    account: str | None = Field(None, max_length=255)
    save_as_note: bool = True


class BriefOut(BaseModel):
    brief: dict
    requirements_restated: list[str]
    note_id: str | None = None
    note_title: str | None = None
    saved: bool = False


@router.post("/brief", response_model=BriefOut)
def read_brief(
    payload: BriefIn,
    db: Session = Depends(get_db),
    principal: Principal = Depends(resolve_principal),
) -> BriefOut:
    brief = extract_customer_brief(payload.requirements)

    note_id: str | None = None
    note_title: str | None = None
    saved = False
    if payload.save_as_note and not brief.is_empty and principal.can_write_catalog:
        workspace = get_or_create_default_workspace(db, principal.org_id)
        try:
            note = save_brief_as_note(
                db,
                org_id=principal.org_id,
                workspace_id=workspace.id,
                brief=brief,
                created_by=principal.user_id,
                account=payload.account,
            )
        except AppError as exc:
            raise HTTPException(status_code=exc.status_code, detail=exc.message) from exc
        note_id, note_title, saved = str(note.id), note.title, True
        record_audit(
            db, principal, "create", "customer_brief", note_id, {"account": payload.account}
        )

    return BriefOut(
        brief=brief.as_dict(),
        requirements_restated=brief.requirement_phrases(),
        note_id=note_id,
        note_title=note_title,
        saved=saved,
    )
