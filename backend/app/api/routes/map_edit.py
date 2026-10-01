"""3.4 Edit the map from the map.

Products, relationships and capabilities already had endpoints. The things 3.2 added --
use cases, room types, platforms, and the links from a product to one of them -- did
not, which meant the only way to correct them was the review queue or Swagger. This
fills the gap so the Map screen can add, rename, and delete everything it draws.

Anything a person creates here is ``confirmed`` and approved on the spot: they are the
source, not a model. Everything is scoped to the caller's org and default workspace.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.catalog.extraction import slugify
from app.db.models import (
    ContextKind,
    CurationStatus,
    EdgeStatus,
    Product,
    ProductContextLink,
    RelationType,
    SellingContext,
)
from app.db.session import get_db
from app.documents.service import get_or_create_default_workspace
from app.security.audit import record_audit
from app.security.deps import resolve_principal
from app.security.principal import Principal

router = APIRouter(prefix="/map", tags=["graph"])


class ContextIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(..., min_length=2, max_length=255)
    kind: str = Field(ContextKind.USE_CASE, max_length=16)
    description: str | None = None
    aliases: list[str] = Field(default_factory=list)


class ContextUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str | None = Field(None, min_length=2, max_length=255)
    description: str | None = None
    aliases: list[str] | None = None


class ContextOut(BaseModel):
    id: str
    kind: str
    reads_as: str
    name: str
    slug: str
    description: str | None = None
    aliases: list[str] = Field(default_factory=list)
    curation_status: str
    is_demo: bool = False
    link_count: int = 0


class ContextLinkIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    product_id: uuid.UUID
    context_id: uuid.UUID
    relation_type: str = RelationType.SUITS_USE_CASE
    evidence: str = Field(..., min_length=3, max_length=4000)
    confidence: float = Field(1.0, ge=0.0, le=1.0)


class ContextLinkOut(BaseModel):
    id: str
    product_id: str
    product_name: str
    context_id: str
    context_name: str
    context_kind: str
    relation_type: str
    reads_as: str
    evidence: str
    confidence: float
    status: str


class RelationWordOut(BaseModel):
    relation_type: str
    reads_as: str
    about: str  # product | context


def _require_writer(principal: Principal) -> None:
    if not principal.can_write_catalog:
        raise HTTPException(status_code=403, detail="you need edit rights to change the map")


def _workspace(db: Session, principal: Principal) -> uuid.UUID:
    return get_or_create_default_workspace(db, principal.org_id).id


def _kind(raw: str | None) -> str:
    cleaned = (raw or ContextKind.USE_CASE).strip().lower().replace(" ", "_").replace("-", "_")
    if cleaned not in ContextKind.ALL:
        raise HTTPException(
            status_code=400,
            detail="That has to be a use case, a room type, or a platform.",
        )
    return cleaned


def _unique_slug(db: Session, workspace_id: uuid.UUID, kind: str, name: str) -> str:
    taken = set(
        db.scalars(
            select(SellingContext.slug).where(
                SellingContext.workspace_id == workspace_id, SellingContext.kind == kind
            )
        ).all()
    )
    base = slugify(name)
    slug = base
    counter = 2
    while slug in taken:
        slug = f"{base}-{counter}"[:128]
        counter += 1
    return slug


def _serialize(context: SellingContext) -> ContextOut:
    return ContextOut(
        id=str(context.id),
        kind=context.kind,
        reads_as=ContextKind.WORDS.get(context.kind, context.kind.replace("_", " ")),
        name=context.name,
        slug=context.slug,
        description=context.description,
        aliases=[str(alias) for alias in (context.aliases or [])],
        curation_status=context.curation_status,
        is_demo=bool(context.is_demo),
        link_count=len(context.product_links or []),
    )


def _serialize_link(link: ProductContextLink) -> ContextLinkOut:
    return ContextLinkOut(
        id=str(link.id),
        product_id=str(link.product_id),
        product_name=link.product.name if link.product else "",
        context_id=str(link.context_id),
        context_name=link.context.name if link.context else "",
        context_kind=link.context.kind if link.context else "",
        relation_type=link.relation_type,
        reads_as=RelationType.words(link.relation_type),
        evidence=link.evidence,
        confidence=link.confidence,
        status=link.status,
    )


def _get_context(db: Session, context_id: uuid.UUID, principal: Principal) -> SellingContext:
    context = db.scalars(
        select(SellingContext).where(
            SellingContext.id == context_id, SellingContext.org_id == principal.org_id
        )
    ).first()
    if context is None:
        raise HTTPException(status_code=404, detail="that is not on the map")
    return context


@router.get("/relation-words", response_model=list[RelationWordOut])
def relation_words() -> list[RelationWordOut]:
    """Every relationship the map understands, in the words a screen should use."""
    return [
        RelationWordOut(
            relation_type=relation,
            reads_as=RelationType.words(relation),
            about="context" if relation in ProductContextLink.CONTEXT_RELATIONS else "product",
        )
        for relation in sorted(RelationType.ALL)
    ]


@router.get("/contexts", response_model=list[ContextOut])
def list_contexts(
    kind: str | None = Query(None),
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0, le=10000),
    db: Session = Depends(get_db),
    principal: Principal = Depends(resolve_principal),
) -> list[ContextOut]:
    workspace_id = _workspace(db, principal)
    stmt = select(SellingContext).where(SellingContext.workspace_id == workspace_id, SellingContext.org_id == principal.org_id)
    if kind:
        stmt = stmt.where(SellingContext.kind == _kind(kind))
    stmt = stmt.order_by(SellingContext.kind.asc(), SellingContext.name.asc())
    return [_serialize(context) for context in db.scalars(stmt.limit(limit).offset(offset)).all()]


@router.post("/contexts", response_model=ContextOut, status_code=status.HTTP_201_CREATED)
def create_context(
    payload: ContextIn,
    db: Session = Depends(get_db),
    principal: Principal = Depends(resolve_principal),
) -> ContextOut:
    _require_writer(principal)
    workspace_id = _workspace(db, principal)
    kind = _kind(payload.kind)
    context = SellingContext(
        org_id=principal.org_id,
        workspace_id=workspace_id,
        kind=kind,
        name=payload.name.strip()[:255],
        slug=_unique_slug(db, workspace_id, kind, payload.name),
        description=payload.description,
        aliases=[alias.strip()[:255] for alias in payload.aliases if alias.strip()][:6] or None,
        curation_status=CurationStatus.CONFIRMED,
        is_ai_suggested=False,
        is_demo=False,
    )
    db.add(context)
    db.commit()
    db.refresh(context)
    record_audit(db, principal, "create", "selling_context", str(context.id), {"kind": kind})
    return _serialize(context)


@router.patch("/contexts/{context_id}", response_model=ContextOut)
def update_context(
    context_id: uuid.UUID,
    payload: ContextUpdate,
    db: Session = Depends(get_db),
    principal: Principal = Depends(resolve_principal),
) -> ContextOut:
    _require_writer(principal)
    context = _get_context(db, context_id, principal)
    if payload.name is not None:
        context.name = payload.name.strip()[:255]
    if payload.description is not None:
        context.description = payload.description
    if payload.aliases is not None:
        context.aliases = [alias.strip()[:255] for alias in payload.aliases if alias.strip()][:6] or None
    # A person editing it is a person owning it.
    context.curation_status = CurationStatus.CONFIRMED
    context.is_demo = False
    db.commit()
    db.refresh(context)
    record_audit(db, principal, "update", "selling_context", str(context.id))
    return _serialize(context)


@router.delete("/contexts/{context_id}")
def delete_context(
    context_id: uuid.UUID,
    db: Session = Depends(get_db),
    principal: Principal = Depends(resolve_principal),
) -> dict:
    _require_writer(principal)
    context = _get_context(db, context_id, principal)
    removed = len(context.product_links or [])
    db.delete(context)
    db.commit()
    record_audit(
        db, principal, "delete", "selling_context", str(context_id), {"links_removed": removed}
    )
    return {"deleted": True, "links_removed": removed}


@router.get("/context-links", response_model=list[ContextLinkOut])
def list_context_links(
    product_id: uuid.UUID | None = Query(None),
    context_id: uuid.UUID | None = Query(None),
    status_filter: str | None = Query(None, alias="status"),
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0, le=10000),
    db: Session = Depends(get_db),
    principal: Principal = Depends(resolve_principal),
) -> list[ContextLinkOut]:
    workspace_id = _workspace(db, principal)
    stmt = select(ProductContextLink).where(ProductContextLink.workspace_id == workspace_id, ProductContextLink.org_id == principal.org_id)
    if product_id is not None:
        stmt = stmt.where(ProductContextLink.product_id == product_id)
    if context_id is not None:
        stmt = stmt.where(ProductContextLink.context_id == context_id)
    if status_filter:
        stmt = stmt.where(ProductContextLink.status == status_filter)
    stmt = stmt.order_by(ProductContextLink.created_at.desc())
    return [_serialize_link(link) for link in db.scalars(stmt.limit(limit).offset(offset)).all()]


@router.post("/context-links", response_model=ContextLinkOut, status_code=status.HTTP_201_CREATED)
def create_context_link(
    payload: ContextLinkIn,
    db: Session = Depends(get_db),
    principal: Principal = Depends(resolve_principal),
) -> ContextLinkOut:
    _require_writer(principal)
    workspace_id = _workspace(db, principal)
    if payload.relation_type not in ProductContextLink.CONTEXT_RELATIONS:
        raise HTTPException(
            status_code=400,
            detail=(
                "A product can suit a use case, be certified for one, or need a licence for "
                "one. Anything else is a relationship between two products."
            ),
        )

    product = db.scalars(
        select(Product).where(
            Product.id == payload.product_id, Product.workspace_id == workspace_id
        )
    ).first()
    context = db.scalars(
        select(SellingContext).where(
            SellingContext.id == payload.context_id,
            SellingContext.workspace_id == workspace_id,
        )
    ).first()
    if product is None or context is None:
        raise HTTPException(status_code=404, detail="both ends have to be on the map first")

    existing = db.scalars(
        select(ProductContextLink).where(
            ProductContextLink.product_id == product.id,
            ProductContextLink.context_id == context.id,
            ProductContextLink.relation_type == payload.relation_type,
        )
    ).first()
    link = existing or ProductContextLink(
        org_id=principal.org_id,
        workspace_id=workspace_id,
        product_id=product.id,
        context_id=context.id,
        relation_type=payload.relation_type,
        evidence=payload.evidence.strip(),
        confidence=payload.confidence,
    )
    link.evidence = payload.evidence.strip()
    link.confidence = payload.confidence
    link.status = EdgeStatus.APPROVED
    link.rejection_reason = None
    link.is_ai_suggested = False
    if existing is None:
        db.add(link)
    product.curation_status = CurationStatus.CONFIRMED
    context.curation_status = CurationStatus.CONFIRMED
    db.commit()
    db.refresh(link)
    record_audit(db, principal, "create", "product_context_link", str(link.id))
    return _serialize_link(link)


@router.delete("/context-links/{link_id}")
def delete_context_link(
    link_id: uuid.UUID,
    db: Session = Depends(get_db),
    principal: Principal = Depends(resolve_principal),
) -> dict:
    _require_writer(principal)
    link = db.scalars(
        select(ProductContextLink).where(
            ProductContextLink.id == link_id, ProductContextLink.org_id == principal.org_id
        )
    ).first()
    if link is None:
        raise HTTPException(status_code=404, detail="that link is not on the map")
    db.delete(link)
    db.commit()
    record_audit(db, principal, "delete", "product_context_link", str(link_id))
    return {"deleted": True}
