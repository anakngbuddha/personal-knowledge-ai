"""3.1 Review what the read step proposed for the product map.

Deliberately small and deliberately separate from the catalog API: this is the queue a
person works through after uploading a vendor PDF, not another way to edit the catalog.
Every response is written in plain words, because the people using it sell things for a
living.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select, func
from sqlalchemy.orm import Session, selectinload

from app.catalog.graph_ingest import GraphIngestor
from app.db.models import (
    CurationStatus,
    Document,
    DocumentStatus,
    EdgeStatus,
    Product,
    ProductContextLink,
    ProductEdge,
    RelationType,
    SellingContext,
)
from app.db.session import get_db
from app.documents.service import get_or_create_default_workspace
from app.security.audit import record_audit
from app.security.deps import resolve_principal
from app.security.principal import Principal

router = APIRouter(prefix="/graph", tags=["graph"])


class SuggestedNodeOut(BaseModel):
    id: str
    name: str
    kind: str
    vendor: str | None = None
    category: str | None = None
    from_source: str | None = None


class SuggestionOut(BaseModel):
    id: str
    kind: str  # relationship | context
    source_name: str
    target_name: str
    relation_type: str
    reads_as: str
    evidence: str
    confidence: float
    page_number: int | None = None
    from_source: str | None = None


class ReviewQueueOut(BaseModel):
    suggestions: list[SuggestionOut] = Field(default_factory=list)
    new_products: list[SuggestedNodeOut] = Field(default_factory=list)
    total: int = 0


class ReadSourceOut(BaseModel):
    document_id: str
    products_created: int
    contexts_created: int
    relationships_suggested: int
    context_links_suggested: int
    read_by: str


class AcceptHighConfidenceIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    min_confidence: float | None = Field(None, ge=0.0, le=1.0)
    document_id: uuid.UUID | None = None


class AcceptHighConfidenceOut(BaseModel):
    min_confidence: float
    relationships_accepted: int
    context_links_accepted: int
    products_confirmed: int
    contexts_confirmed: int


class RejectIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    reason: str = Field("Not right for our map", min_length=1, max_length=500)


def _require_writer(principal: Principal) -> None:
    if not principal.can_write_catalog:
        raise HTTPException(status_code=403, detail="you need edit rights to change the map")


@router.post("/read/{document_id}", response_model=ReadSourceOut)
def read_source(
    document_id: uuid.UUID,
    db: Session = Depends(get_db),
    principal: Principal = Depends(resolve_principal),
) -> ReadSourceOut:
    """Read one source again and propose what it says for the map."""
    _require_writer(principal)
    document = db.scalars(
        select(Document).where(Document.id == document_id, Document.org_id == principal.org_id)
    ).first()
    if document is None:
        raise HTTPException(status_code=404, detail="that source is not here")
    if document.status != DocumentStatus.READY:
        raise HTTPException(status_code=409, detail="that source is not ready to read yet")

    summary = GraphIngestor(db).ingest_document(document)
    record_audit(
        db, principal, "read_for_map", "document", str(document.id), summary.as_dict()
    )
    return ReadSourceOut(
        document_id=str(document.id),
        products_created=summary.products_created,
        contexts_created=summary.contexts_created,
        relationships_suggested=summary.edges_created,
        context_links_suggested=summary.context_links_created,
        read_by=summary.origin,
    )


@router.get("/review-queue", response_model=ReviewQueueOut)
def review_queue(
    document_id: uuid.UUID | None = Query(None),
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0, le=10000),
    db: Session = Depends(get_db),
    principal: Principal = Depends(resolve_principal),
) -> ReviewQueueOut:
    """Everything waiting on a person, relationships first."""
    workspace = get_or_create_default_workspace(db, principal.org_id)

    edge_stmt = (
        select(ProductEdge)
        .options(selectinload(ProductEdge.source_product), selectinload(ProductEdge.target_product), selectinload(ProductEdge.document))
        .where(
            ProductEdge.workspace_id == workspace.id,
            ProductEdge.status == EdgeStatus.PENDING_REVIEW,
        )
        .order_by(ProductEdge.confidence.desc())
        .limit(limit).offset(offset)
    )
    link_stmt = (
        select(ProductContextLink)
        .options(selectinload(ProductContextLink.product), selectinload(ProductContextLink.context), selectinload(ProductContextLink.document))
        .where(
            ProductContextLink.workspace_id == workspace.id,
            ProductContextLink.status == EdgeStatus.PENDING_REVIEW,
        )
        .order_by(ProductContextLink.confidence.desc())
        .limit(limit).offset(offset)
    )
    if document_id is not None:
        edge_stmt = edge_stmt.where(ProductEdge.document_id == document_id)
        link_stmt = link_stmt.where(ProductContextLink.document_id == document_id)

    suggestions: list[SuggestionOut] = []
    for edge in db.scalars(edge_stmt).all():
        suggestions.append(
            SuggestionOut(
                id=str(edge.id),
                kind="relationship",
                source_name=edge.source_product.name if edge.source_product else "",
                target_name=edge.target_product.name if edge.target_product else "",
                relation_type=edge.relation_type,
                reads_as=RelationType.words(edge.relation_type),
                evidence=edge.evidence,
                confidence=edge.confidence,
                page_number=edge.page_number,
                from_source=edge.document.original_filename if edge.document else None,
            )
        )
    for link in db.scalars(link_stmt).all():
        suggestions.append(
            SuggestionOut(
                id=str(link.id),
                kind="context",
                source_name=link.product.name if link.product else "",
                target_name=link.context.name if link.context else "",
                relation_type=link.relation_type,
                reads_as=RelationType.words(link.relation_type),
                evidence=link.evidence,
                confidence=link.confidence,
                page_number=link.page_number,
                from_source=link.document.original_filename if link.document else None,
            )
        )

    product_stmt = (
        select(Product)
        .where(
            Product.workspace_id == workspace.id,
            Product.curation_status == CurationStatus.SUGGESTED,
        )
        .order_by(Product.created_at.desc())
        .limit(limit).offset(offset)
    )
    if document_id is not None:
        product_stmt = product_stmt.where(Product.source_document_id == document_id)

    new_products = [
        SuggestedNodeOut(
            id=str(product.id),
            name=product.name,
            kind="product",
            vendor=product.vendor,
            category=product.category,
        )
        for product in db.scalars(product_stmt).all()
    ]

    context_stmt = (
        select(SellingContext)
        .where(
            SellingContext.workspace_id == workspace.id,
            SellingContext.curation_status == CurationStatus.SUGGESTED,
        )
        .order_by(SellingContext.created_at.desc())
        .limit(limit).offset(offset)
    )
    if document_id is not None:
        context_stmt = context_stmt.where(SellingContext.source_document_id == document_id)
    new_products.extend(
        SuggestedNodeOut(id=str(context.id), name=context.name, kind=context.kind)
        for context in db.scalars(context_stmt).all()
    )

    return ReviewQueueOut(
        suggestions=suggestions, new_products=new_products,
        total=sum(db.scalar(select(func.count()).select_from(stmt.limit(None).offset(None).order_by(None).subquery())) or 0 for stmt in (edge_stmt, link_stmt))
    )


@router.post("/accept-high-confidence", response_model=AcceptHighConfidenceOut)
def accept_high_confidence(
    payload: AcceptHighConfidenceIn | None = None,
    db: Session = Depends(get_db),
    principal: Principal = Depends(resolve_principal),
) -> AcceptHighConfidenceOut:
    """Accept every waiting suggestion we are confident about."""
    _require_writer(principal)
    body = payload or AcceptHighConfidenceIn()
    workspace = get_or_create_default_workspace(db, principal.org_id)
    result = GraphIngestor(db).accept_high_confidence(
        org_id=principal.org_id,
        workspace_id=workspace.id,
        min_confidence=body.min_confidence,
        document_id=body.document_id,
    )
    record_audit(db, principal, "bulk_accept", "product_edge", None, result)
    return AcceptHighConfidenceOut(**result)


@router.post("/context-links/{link_id}/approve", response_model=SuggestionOut)
def approve_context_link(
    link_id: uuid.UUID,
    db: Session = Depends(get_db),
    principal: Principal = Depends(resolve_principal),
) -> SuggestionOut:
    _require_writer(principal)
    link = _get_link(db, link_id, principal)
    link.status = EdgeStatus.APPROVED
    link.rejection_reason = None
    if link.product is not None:
        link.product.curation_status = CurationStatus.CONFIRMED
    if link.context is not None:
        link.context.curation_status = CurationStatus.CONFIRMED
    db.commit()
    db.refresh(link)
    record_audit(db, principal, "approve", "product_context_link", str(link.id))
    return _serialize_link(link)


@router.post("/context-links/{link_id}/reject", response_model=SuggestionOut)
def reject_context_link(
    link_id: uuid.UUID,
    payload: RejectIn,
    db: Session = Depends(get_db),
    principal: Principal = Depends(resolve_principal),
) -> SuggestionOut:
    _require_writer(principal)
    link = _get_link(db, link_id, principal)
    link.status = EdgeStatus.REJECTED
    link.rejection_reason = payload.reason
    db.commit()
    db.refresh(link)
    record_audit(
        db, principal, "reject", "product_context_link", str(link.id), {"reason": payload.reason}
    )
    return _serialize_link(link)


def _get_link(db: Session, link_id: uuid.UUID, principal: Principal) -> ProductContextLink:
    link = db.scalars(
        select(ProductContextLink).where(
            ProductContextLink.id == link_id,
            ProductContextLink.org_id == principal.org_id,
        )
    ).first()
    if link is None:
        raise HTTPException(status_code=404, detail="that suggestion is not here")
    return link


def _serialize_link(link: ProductContextLink) -> SuggestionOut:
    return SuggestionOut(
        id=str(link.id),
        kind="context",
        source_name=link.product.name if link.product else "",
        target_name=link.context.name if link.context else "",
        relation_type=link.relation_type,
        reads_as=RelationType.words(link.relation_type),
        evidence=link.evidence,
        confidence=link.confidence,
        page_number=link.page_number,
        from_source=link.document.original_filename if link.document else None,
    )
