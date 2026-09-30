"""Human-reviewed sales statements with versioned, access-controlled citations."""

from __future__ import annotations

import re
import uuid
from datetime import date, datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.api.routes.opportunities import _require_sales, _visible_opportunity
from app.db.models import Document, SalesClaim
from app.db.session import get_db
from app.retrieval.access import get_readable_document, readable_documents
from app.security.audit import record_audit
from app.security.deps import resolve_principal
from app.security.labels import ApprovalState, Sensitivity
from app.security.principal import Principal

router = APIRouter(prefix="/api/sales", tags=["sales-claims"])


class ClaimIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    statement: str = Field(min_length=1, max_length=4000)
    competitor: str | None = Field(default=None, max_length=255)
    source_document_id: uuid.UUID
    source_anchor: str = Field(min_length=1, max_length=512)
    valid_until: date


class ClaimDecision(BaseModel):
    model_config = ConfigDict(extra="forbid")
    version: int = Field(ge=1)
    reason: str = Field(min_length=1, max_length=2000)


class ClaimOut(ClaimIn):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    status: str
    source_version: int
    source_content_hash: str
    version: int
    reviewer_id: uuid.UUID | None
    review_reason: str | None


def _source(db, principal, row, *, approved=False):
    doc = get_readable_document(db, principal, row.source_document_id)
    if doc is None:
        raise HTTPException(404, "claim source is unavailable")
    if doc.version != row.source_version or doc.content_hash != row.source_content_hash:
        raise HTTPException(409, "claim source version changed; create a new claim")
    today = datetime.now(timezone.utc).date()
    if row.valid_until < today or (doc.valid_until is not None and doc.valid_until < today):
        raise HTTPException(409, "claim or source has expired")
    if approved and doc.approval_state != ApprovalState.APPROVED:
        raise HTTPException(409, "source must be approved before reusing a claim")
    return doc


def _claim(db, principal, claim_id, *, write=False):
    row = db.scalars(select(SalesClaim).where(
        SalesClaim.id == claim_id, SalesClaim.org_id == principal.org_id,
    )).first()
    if row is None:
        raise HTTPException(404, "claim not found")
    _visible_opportunity(db, principal, row.opportunity_id, write=write)
    _source(db, principal, row)
    return row


@router.post("/opportunities/{opportunity_id}/claims", response_model=ClaimOut, status_code=201)
def create_claim(opportunity_id: uuid.UUID, payload: ClaimIn, db: Session = Depends(get_db),
                 principal: Principal = Depends(resolve_principal)):
    _require_sales(principal)
    if principal.user_id is None:
        raise HTTPException(403, "an identified author is required")
    opportunity = _visible_opportunity(db, principal, opportunity_id, write=True)
    doc = get_readable_document(db, principal, payload.source_document_id)
    if doc is None or doc.workspace_id != opportunity.workspace_id:
        raise HTTPException(404, "source not found in the opportunity workspace")
    if not doc.content_hash or not re.fullmatch(r"[a-f0-9]{64}", doc.content_hash):
        raise HTTPException(409, "source content checksum is required")
    if not payload.statement.strip() or not payload.source_anchor.strip():
        raise HTTPException(422, "statement and source anchor must contain text")
    if payload.valid_until < datetime.now(timezone.utc).date() or (
        doc.valid_until is not None and payload.valid_until > doc.valid_until
    ):
        raise HTTPException(422, "claim validity must fit the source validity period")
    row = SalesClaim(org_id=principal.org_id, opportunity_id=opportunity_id,
                     source_version=doc.version, source_content_hash=doc.content_hash,
                     created_by=principal.user_id, **payload.model_dump())
    db.add(row)
    db.flush()
    record_audit(db, principal, "create", "sales_claim", str(row.id), {"source_id": str(doc.id), "source_version": doc.version})
    db.refresh(row)
    return row


@router.get("/opportunities/{opportunity_id}/claim-sources")
def list_claim_sources(opportunity_id: uuid.UUID, limit: int = Query(50, ge=1, le=100), offset: int = Query(0, ge=0),
                       db: Session = Depends(get_db), principal: Principal = Depends(resolve_principal)):
    _require_sales(principal)
    opportunity = _visible_opportunity(db, principal, opportunity_id)
    rows = db.scalars(readable_documents(principal).where(
        Document.workspace_id == opportunity.workspace_id, Document.content_hash.is_not(None),
    ).order_by(Document.uploaded_at.desc(), Document.id).limit(limit).offset(offset)).all()
    record_audit(db, principal, "list_sources", "sales_claim", str(opportunity_id), {"count": len(rows)})
    return {"items": [{"id": str(doc.id), "title": doc.title or doc.original_filename,
                       "approval_state": doc.approval_state, "version": doc.version} for doc in rows],
            "limit": limit, "offset": offset}


@router.get("/opportunities/{opportunity_id}/claims")
def list_claims(opportunity_id: uuid.UUID, limit: int = Query(50, ge=1, le=100), offset: int = Query(0, ge=0),
                db: Session = Depends(get_db), principal: Principal = Depends(resolve_principal)):
    _require_sales(principal)
    _visible_opportunity(db, principal, opportunity_id)
    permitted_ids = readable_documents(principal).with_only_columns(Document.id)
    rows = db.scalars(select(SalesClaim).where(
        SalesClaim.org_id == principal.org_id, SalesClaim.opportunity_id == opportunity_id,
        SalesClaim.source_document_id.in_(permitted_ids),
    ).order_by(SalesClaim.created_at.desc(), SalesClaim.id).limit(limit).offset(offset)).all()
    record_audit(db, principal, "list", "sales_claim", str(opportunity_id), {"count": len(rows)})
    return {"items": [ClaimOut.model_validate(row) for row in rows], "limit": limit, "offset": offset}


@router.post("/claims/{claim_id}/approve", response_model=ClaimOut)
def approve_claim(claim_id: uuid.UUID, payload: ClaimDecision, db: Session = Depends(get_db),
                  principal: Principal = Depends(resolve_principal)):
    if not principal.can_write_catalog or principal.user_id is None:
        raise HTTPException(403, "an identified solutions engineer reviewer is required")
    row = _claim(db, principal, claim_id, write=True)
    if row.created_by == principal.user_id:
        raise HTTPException(403, "a separate reviewer must approve the claim")
    _source(db, principal, row, approved=True)
    changed = db.execute(update(SalesClaim).where(
        SalesClaim.id == row.id, SalesClaim.org_id == principal.org_id,
        SalesClaim.status == "draft", SalesClaim.version == payload.version,
    ).values(status="approved", version=SalesClaim.version + 1,
             reviewer_id=principal.user_id, reviewed_at=datetime.now(timezone.utc), review_reason=payload.reason))
    if changed.rowcount != 1:
        db.rollback()
        raise HTTPException(409, "claim state or version changed")
    record_audit(db, principal, "approve", "sales_claim", str(row.id), {"version": payload.version})
    db.refresh(row)
    return row


@router.post("/claims/{claim_id}/revoke")
def revoke_claim(claim_id: uuid.UUID, payload: ClaimDecision, db: Session = Depends(get_db),
                 principal: Principal = Depends(resolve_principal)):
    if not principal.can_write_catalog or principal.user_id is None:
        raise HTTPException(403, "solutions engineer reviewer required")
    # Revocation must remain possible after a source expires or becomes unreadable.
    row = db.scalars(select(SalesClaim).where(SalesClaim.id == claim_id, SalesClaim.org_id == principal.org_id)).first()
    if row is None:
        raise HTTPException(404, "claim not found")
    _visible_opportunity(db, principal, row.opportunity_id, write=True)
    changed = db.execute(update(SalesClaim).where(
        SalesClaim.id == row.id, SalesClaim.org_id == principal.org_id,
        SalesClaim.version == payload.version, SalesClaim.status != "revoked",
    ).values(status="revoked", version=SalesClaim.version + 1, review_reason=payload.reason,
             reviewer_id=principal.user_id, reviewed_at=datetime.now(timezone.utc)))
    if changed.rowcount != 1:
        db.rollback()
        raise HTTPException(409, "claim state or version changed")
    record_audit(db, principal, "revoke", "sales_claim", str(row.id))
    db.refresh(row)
    return {"id": str(row.id), "status": row.status, "version": row.version}


@router.get("/opportunities/{opportunity_id}/battle-card")
def export_battle_card(opportunity_id: uuid.UUID, limit: int = Query(50, ge=1, le=100), offset: int = Query(0, ge=0),
                       db: Session = Depends(get_db), principal: Principal = Depends(resolve_principal)):
    _require_sales(principal)
    _visible_opportunity(db, principal, opportunity_id)
    permitted_ids = readable_documents(principal).with_only_columns(Document.id)
    rows = db.scalars(select(SalesClaim).where(
        SalesClaim.org_id == principal.org_id, SalesClaim.opportunity_id == opportunity_id,
        SalesClaim.status == "approved", SalesClaim.source_document_id.in_(permitted_ids),
    ).order_by(SalesClaim.created_at, SalesClaim.id).limit(limit).offset(offset)).all()
    items = []
    for row in rows:
        try:
            doc = _source(db, principal, row, approved=True)
        except HTTPException as exc:
            if exc.status_code in (404, 409):
                continue
            raise
        # Battle-card export is customer safe even for an administrator.
        if doc.sensitivity != Sensitivity.PUBLIC or doc.account_ref is not None:
            continue
        items.append({"id": str(row.id), "statement": row.statement, "competitor": row.competitor,
                      "valid_until": row.valid_until.isoformat(), "reviewer_id": str(row.reviewer_id),
                      "source": {"document_id": str(doc.id), "version": row.source_version,
                                 "content_hash": row.source_content_hash, "anchor": row.source_anchor,
                                 "url": doc.source_url}})
    record_audit(db, principal, "export", "sales_battle_card", str(opportunity_id), {"count": len(items)})
    return {"items": items, "limit": limit, "offset": offset, "generated_at": datetime.now(timezone.utc).isoformat()}
