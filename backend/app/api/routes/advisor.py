"""4.1 Customer brief and 4.2 advisor API.

One endpoint per action the salesperson actually takes:

``POST /advisor/brief``
    They paste what the customer sent, and get back a brief they can read, correct, and
    keep. Saving it as a note is the default, so the brief is searchable and editable in
    Notes like anything written by hand, and so the rest of the conversation can
    retrieve it. Editing a brief is editing its note; there is deliberately no second
    write path.

``POST /advisor/recommend``
    The question after that: "what can I add from my product list?" Returns the bundle
    by requirement, the clashes and prerequisites read off the map, what the product list
    cannot cover, upsell and cross-sell, the questions still worth asking, and the
    assumptions a human has to verify. Optionally saved as a note in one call.

``POST /advisor/recommend/export``
    The same recommendation as a Word file or a deck. Stateless on purpose: the request
    carries the requirements, so there is no server-side draft to expire, leak, or
    clean up.
"""

from __future__ import annotations

import io
import uuid

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from app.advisor.brief import extract_customer_brief, save_brief_as_note
from app.advisor.export import DOCX_MIME, PPTX_MIME, filename_for, to_docx, to_pptx
from app.advisor.service import build_recommendation
from app.core.errors import AppError
from app.db.session import get_db
from app.documents.service import get_or_create_default_workspace
from app.notes import service as notes_service
from app.security.audit import record_audit
from app.security.deps import resolve_principal
from app.security.principal import Principal

router = APIRouter(prefix="/advisor", tags=["advisor"])


def _notebook_uuid(value: str | None) -> uuid.UUID | None:
    if not value:
        return None
    try:
        return uuid.UUID(value)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="That notebook id is not valid.") from exc


class BriefIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    requirements: str = Field(..., min_length=1, max_length=200_000)
    account: str | None = Field(None, max_length=255)
    save_as_note: bool = True
    notebook_id: str | None = Field(None, max_length=64)


class BriefOut(BaseModel):
    brief: dict
    requirements_restated: list[str]
    note_id: str | None = None
    note_title: str | None = None
    saved: bool = False


class RecommendIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    requirements: str = Field(..., min_length=1, max_length=200_000)
    account: str | None = Field(None, max_length=255)
    save_as_note: bool = False
    notebook_id: str | None = Field(None, max_length=64)


class RecommendOut(BaseModel):
    brief: dict
    recommendation: dict
    markdown: str
    note_id: str | None = None
    note_title: str | None = None
    saved: bool = False


class ExportIn(RecommendIn):
    model_config = ConfigDict(extra="forbid")

    format: str = Field("docx", pattern="^(docx|pptx)$")


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
                notebook_id=_notebook_uuid(payload.notebook_id),
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


@router.post("/recommend", response_model=RecommendOut)
def recommend(
    payload: RecommendIn,
    db: Session = Depends(get_db),
    principal: Principal = Depends(resolve_principal),
) -> RecommendOut:
    workspace = get_or_create_default_workspace(db, principal.org_id)
    brief = extract_customer_brief(payload.requirements)
    result = build_recommendation(
        db, principal=principal, workspace_id=workspace.id, brief=brief
    )
    markdown = result.as_markdown()

    note_id: str | None = None
    note_title: str | None = None
    saved = False
    if payload.save_as_note and principal.can_write_catalog:
        body = markdown
        if payload.account:
            body = f"Account: [[account:{payload.account}]]\n\n{markdown}"
        try:
            note = notes_service.create_note(
                db,
                org_id=principal.org_id,
                workspace_id=workspace.id,
                title=result.note_title(),
                body=body,
                created_by=principal.user_id,
                notebook_id=_notebook_uuid(payload.notebook_id),
            )
        except AppError as exc:
            raise HTTPException(status_code=exc.status_code, detail=exc.message) from exc
        note_id, note_title, saved = str(note.id), note.title, True

    record_audit(
        db,
        principal,
        "run",
        "advisor_recommendation",
        note_id,
        {"account": payload.account, "products": len(result.picks), "gaps": len(result.gaps)},
    )
    return RecommendOut(
        brief=brief.as_dict(),
        recommendation=result.as_dict(),
        markdown=markdown,
        note_id=note_id,
        note_title=note_title,
        saved=saved,
    )


@router.post("/recommend/export")
def export_recommendation(
    payload: ExportIn,
    db: Session = Depends(get_db),
    principal: Principal = Depends(resolve_principal),
) -> StreamingResponse:
    workspace = get_or_create_default_workspace(db, principal.org_id)
    brief = extract_customer_brief(payload.requirements)
    result = build_recommendation(
        db, principal=principal, workspace_id=workspace.id, brief=brief
    )

    if payload.format == "pptx":
        data, mime, extension = to_pptx(result), PPTX_MIME, "pptx"
    else:
        data, mime, extension = to_docx(result), DOCX_MIME, "docx"

    filename = filename_for(result, extension)
    record_audit(
        db,
        principal,
        "export",
        "advisor_recommendation",
        None,
        {"format": extension, "bytes": len(data)},
    )
    return StreamingResponse(
        io.BytesIO(data),
        media_type=mime,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
