from __future__ import annotations

import uuid
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.catalog.auto_graph import suggest_solution_graph
from app.catalog.curation import EdgeSuggestionEngine
from app.catalog.demo import DISABLED_MESSAGE, demo_catalog_enabled, seed_demo_catalog
from app.catalog.models import (
    AutoGraphOut,
    CapabilityIn,
    CapabilityOut,
    ContextLinkOut,
    CoverageReportOut,
    EdgeActionIn,
    EdgeSuggestionOut,
    GraphQueryOut,
    IntegrityReportOut,
    NeighborhoodOut,
    PortfolioGraphOut,
    ProductCapabilityIn,
    ProductCapabilityOut,
    ProductDetailOut,
    ProductEdgeIn,
    ProductEdgeOut,
    ProductEdgeUpdate,
    ProductIn,
    ProductOut,
    ProductUpdate,
    ReferenceArchitectureIn,
    ReferenceArchitectureOut,
    ReferenceArchitectureProductOut,
)
from app.catalog.service import CatalogService
from app.core.errors import AppError, ProviderError, ProviderRateLimited
from app.core.logging import get_logger
from app.db.models import Document, EdgeStatus, Product
from app.db.session import get_db
from app.documents.service import get_or_create_default_workspace
from app.security.deps import resolve_principal
from app.security.principal import Principal

logger = get_logger(__name__)
router = APIRouter(tags=["catalog", "graph"])


def _get_service(
    db: Session = Depends(get_db),
    principal: Principal = Depends(resolve_principal),
) -> tuple[CatalogService, uuid.UUID, uuid.UUID]:
    workspace = get_or_create_default_workspace(db, principal.org_id)
    return CatalogService(db), principal.org_id, workspace.id


# ---------------------------------------------------------------------------
# Products Endpoints
# ---------------------------------------------------------------------------


@router.get("/catalog/products", response_model=list[ProductOut])
def list_products(
    vendor: str | None = Query(None),
    ownership: str | None = Query(None),
    category: str | None = Query(None),
    lifecycle_status: str | None = Query(None),
    search: str | None = Query(None),
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    deps: tuple[CatalogService, uuid.UUID, uuid.UUID] = Depends(_get_service),
) -> list[ProductOut]:
    service, _, workspace_id = deps
    products = service.list_products(
        workspace_id=workspace_id,
        vendor=vendor,
        ownership=ownership,
        category=category,
        lifecycle_status=lifecycle_status,
        search=search,
        limit=limit,
        offset=offset,
    )
    result: list[ProductOut] = []
    for p in products:
        p_out = ProductOut.model_validate(p)
        p_out.capabilities = [
            ProductCapabilityOut(
                capability_id=pc.capability.id,
                name=pc.capability.name,
                slug=pc.capability.slug,
                category=pc.capability.category,
                description=pc.capability.description,
                proficiency=pc.proficiency,
                notes=pc.notes,
            )
            for pc in p.capabilities
        ]
        result.append(p_out)
    return result


@router.post("/catalog/products", response_model=ProductOut, status_code=status.HTTP_201_CREATED)
def create_product(
    data: ProductIn,
    deps: tuple[CatalogService, uuid.UUID, uuid.UUID] = Depends(_get_service),
) -> ProductOut:
    service, org_id, workspace_id = deps
    product = service.create_product(org_id, workspace_id, data)
    return ProductOut.model_validate(product)


@router.get("/catalog/products/{product_id}", response_model=ProductDetailOut)
def get_product(
    product_id: uuid.UUID,
    deps: tuple[CatalogService, uuid.UUID, uuid.UUID] = Depends(_get_service),
    db: Session = Depends(get_db),
) -> ProductDetailOut:
    service, _, workspace_id = deps
    product = service.get_product(product_id, workspace_id)
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")

    p_out = ProductDetailOut.model_validate(product)
    p_out.capabilities = [
        ProductCapabilityOut(
            capability_id=pc.capability.id,
            name=pc.capability.name,
            slug=pc.capability.slug,
            category=pc.capability.category,
            description=pc.capability.description,
            proficiency=pc.proficiency,
            notes=pc.notes,
        )
        for pc in product.capabilities
    ]

    # Map outgoing edges
    all_prods = {p.id: p.name for p in service.list_products(workspace_id, limit=500)}
    p_out.outgoing_edges = [
        ProductEdgeOut(
            id=e.id,
            org_id=e.org_id,
            workspace_id=e.workspace_id,
            source_product_id=e.source_product_id,
            source_product_name=all_prods.get(e.source_product_id, "Unknown"),
            target_product_id=e.target_product_id,
            target_product_name=all_prods.get(e.target_product_id, "Unknown"),
            relation_type=e.relation_type,
            evidence=e.evidence,
            confidence=e.confidence,
            document_id=e.document_id,
            is_ai_suggested=e.is_ai_suggested,
            status=e.status,
            rejection_reason=e.rejection_reason,
            created_at=e.created_at,
        )
        for e in product.outgoing_edges
        if e.status == EdgeStatus.APPROVED
    ]
    p_out.incoming_edges = [
        ProductEdgeOut(
            id=e.id,
            org_id=e.org_id,
            workspace_id=e.workspace_id,
            source_product_id=e.source_product_id,
            source_product_name=all_prods.get(e.source_product_id, "Unknown"),
            target_product_id=e.target_product_id,
            target_product_name=all_prods.get(e.target_product_id, "Unknown"),
            relation_type=e.relation_type,
            evidence=e.evidence,
            confidence=e.confidence,
            document_id=e.document_id,
            is_ai_suggested=e.is_ai_suggested,
            status=e.status,
            rejection_reason=e.rejection_reason,
            created_at=e.created_at,
        )
        for e in product.incoming_edges
        if e.status == EdgeStatus.APPROVED
    ]

    # Map reference architectures
    p_out.reference_architectures = [
        ReferenceArchitectureOut(
            id=rap.architecture.id,
            org_id=rap.architecture.org_id,
            workspace_id=rap.architecture.workspace_id,
            name=rap.architecture.name,
            slug=rap.architecture.slug,
            description=rap.architecture.description,
            architecture_overview=rap.architecture.architecture_overview,
            target_segment=rap.architecture.target_segment,
            created_at=rap.architecture.created_at,
            products=[
                ReferenceArchitectureProductOut(
                    product_id=p_item.product_id,
                    product_name=all_prods.get(p_item.product_id, "Unknown"),
                    vendor="",
                    ownership="",
                    category="",
                    role=p_item.role,
                    notes=p_item.notes,
                )
                for p_item in rap.architecture.products
            ],
        )
        for rap in product.reference_architectures
    ]

    # Find collateral documents
    doc_ids = product.collateral_document_ids or []
    if doc_ids:
        docs = list(db.scalars(select(Document).where(Document.id.in_(doc_ids))).all())
        p_out.collateral_documents = [
            {"id": str(d.id), "title": d.title, "filename": d.original_filename, "file_type": d.file_type}
            for d in docs
        ]

    return p_out


@router.patch("/catalog/products/{product_id}", response_model=ProductOut)
def update_product(
    product_id: uuid.UUID,
    data: ProductUpdate,
    deps: tuple[CatalogService, uuid.UUID, uuid.UUID] = Depends(_get_service),
) -> ProductOut:
    service, _, workspace_id = deps
    updated = service.update_product(product_id, workspace_id, data)
    if not updated:
        raise HTTPException(status_code=404, detail="Product not found")
    return ProductOut.model_validate(updated)


@router.delete("/catalog/products/{product_id}")
def delete_product(
    product_id: uuid.UUID,
    deps: tuple[CatalogService, uuid.UUID, uuid.UUID] = Depends(_get_service),
) -> dict[str, bool]:
    service, _, workspace_id = deps
    ok = service.delete_product(product_id, workspace_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Product not found")
    return {"deleted": True}


# ---------------------------------------------------------------------------
# Capabilities Endpoints
# ---------------------------------------------------------------------------


@router.get("/catalog/capabilities", response_model=list[CapabilityOut])
def list_capabilities(
    category: str | None = Query(None),
    deps: tuple[CatalogService, uuid.UUID, uuid.UUID] = Depends(_get_service),
) -> list[CapabilityOut]:
    service, org_id, _ = deps
    caps = service.list_capabilities(org_id, category=category)
    result: list[CapabilityOut] = []
    for c in caps:
        c_out = CapabilityOut.model_validate(c)
        c_out.product_count = len(c.products)
        result.append(c_out)
    return result


@router.post("/catalog/capabilities", response_model=CapabilityOut, status_code=status.HTTP_201_CREATED)
def create_capability(
    data: CapabilityIn,
    deps: tuple[CatalogService, uuid.UUID, uuid.UUID] = Depends(_get_service),
) -> CapabilityOut:
    service, org_id, _ = deps
    cap = service.create_capability(org_id, data)
    c_out = CapabilityOut.model_validate(cap)
    c_out.product_count = len(cap.products)
    return c_out


@router.post("/catalog/products/{product_id}/capabilities", response_model=ProductCapabilityOut)
def assign_capability(
    product_id: uuid.UUID,
    data: ProductCapabilityIn,
    deps: tuple[CatalogService, uuid.UUID, uuid.UUID] = Depends(_get_service),
) -> ProductCapabilityOut:
    service, _, workspace_id = deps
    pc = service.assign_capability_to_product(product_id, workspace_id, data)
    return ProductCapabilityOut(
        capability_id=pc.capability.id,
        name=pc.capability.name,
        slug=pc.capability.slug,
        category=pc.capability.category,
        description=pc.capability.description,
        proficiency=pc.proficiency,
        notes=pc.notes,
    )


@router.delete("/catalog/products/{product_id}/capabilities/{capability_id}")
def remove_capability(
    product_id: uuid.UUID,
    capability_id: uuid.UUID,
    deps: tuple[CatalogService, uuid.UUID, uuid.UUID] = Depends(_get_service),
) -> dict[str, bool]:
    service, _, workspace_id = deps
    ok = service.remove_capability_from_product(product_id, capability_id, workspace_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Capability assignment not found")
    return {"removed": True}


# ---------------------------------------------------------------------------
# Product Edges Endpoints & Curation
# ---------------------------------------------------------------------------


@router.get("/graph/edges", response_model=list[ProductEdgeOut])
def list_edges(
    status: str | None = Query(None),
    relation_type: str | None = Query(None),
    product_id: uuid.UUID | None = Query(None),
    deps: tuple[CatalogService, uuid.UUID, uuid.UUID] = Depends(_get_service),
) -> list[ProductEdgeOut]:
    service, _, workspace_id = deps
    edges = service.list_edges(
        workspace_id=workspace_id,
        status=status,
        relation_type=relation_type,
        product_id=product_id,
    )
    all_prods = {p.id: p.name for p in service.list_products(workspace_id, limit=500)}
    return [
        ProductEdgeOut(
            id=e.id,
            org_id=e.org_id,
            workspace_id=e.workspace_id,
            source_product_id=e.source_product_id,
            source_product_name=all_prods.get(e.source_product_id, "Unknown"),
            target_product_id=e.target_product_id,
            target_product_name=all_prods.get(e.target_product_id, "Unknown"),
            relation_type=e.relation_type,
            evidence=e.evidence,
            confidence=e.confidence,
            document_id=e.document_id,
            is_ai_suggested=e.is_ai_suggested,
            status=e.status,
            rejection_reason=e.rejection_reason,
            created_at=e.created_at,
        )
        for e in edges
    ]


@router.post("/graph/edges", response_model=ProductEdgeOut, status_code=status.HTTP_201_CREATED)
def create_edge(
    data: ProductEdgeIn,
    deps: tuple[CatalogService, uuid.UUID, uuid.UUID] = Depends(_get_service),
) -> ProductEdgeOut:
    service, org_id, workspace_id = deps
    edge = service.create_edge(org_id, workspace_id, data)
    all_prods = {p.id: p.name for p in service.list_products(workspace_id, limit=500)}
    return ProductEdgeOut(
        id=edge.id,
        org_id=edge.org_id,
        workspace_id=edge.workspace_id,
        source_product_id=edge.source_product_id,
        source_product_name=all_prods.get(edge.source_product_id, "Unknown"),
        target_product_id=edge.target_product_id,
        target_product_name=all_prods.get(edge.target_product_id, "Unknown"),
        relation_type=edge.relation_type,
        evidence=edge.evidence,
        confidence=edge.confidence,
        document_id=edge.document_id,
        is_ai_suggested=edge.is_ai_suggested,
        status=edge.status,
        rejection_reason=edge.rejection_reason,
        created_at=edge.created_at,
    )


@router.patch("/graph/edges/{edge_id}", response_model=ProductEdgeOut)
def update_edge(
    edge_id: uuid.UUID,
    data: ProductEdgeUpdate,
    deps: tuple[CatalogService, uuid.UUID, uuid.UUID] = Depends(_get_service),
) -> ProductEdgeOut:
    service, _, workspace_id = deps
    edge = service.update_edge(edge_id, workspace_id, data)
    if not edge:
        raise HTTPException(status_code=404, detail="Edge not found")
    all_prods = {p.id: p.name for p in service.list_products(workspace_id, limit=500)}
    return ProductEdgeOut(
        id=edge.id,
        org_id=edge.org_id,
        workspace_id=edge.workspace_id,
        source_product_id=edge.source_product_id,
        source_product_name=all_prods.get(edge.source_product_id, "Unknown"),
        target_product_id=edge.target_product_id,
        target_product_name=all_prods.get(edge.target_product_id, "Unknown"),
        relation_type=edge.relation_type,
        evidence=edge.evidence,
        confidence=edge.confidence,
        document_id=edge.document_id,
        is_ai_suggested=edge.is_ai_suggested,
        status=edge.status,
        rejection_reason=edge.rejection_reason,
        created_at=edge.created_at,
    )


@router.delete("/graph/edges/{edge_id}")
def delete_edge(
    edge_id: uuid.UUID,
    deps: tuple[CatalogService, uuid.UUID, uuid.UUID] = Depends(_get_service),
) -> dict[str, bool]:
    service, _, workspace_id = deps
    ok = service.delete_edge(edge_id, workspace_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Edge not found")
    return {"deleted": True}


@router.post("/graph/suggest-edges", response_model=list[EdgeSuggestionOut])
def suggest_edges(
    deps: tuple[CatalogService, uuid.UUID, uuid.UUID] = Depends(_get_service),
    db: Session = Depends(get_db),
) -> list[EdgeSuggestionOut]:
    """Scan ingested source documents for implied product relationships."""
    service, org_id, workspace_id = deps
    engine = EdgeSuggestionEngine(db)
    suggestions = engine.suggest_edges_from_documents(workspace_id, org_id)

    all_prods = {p.id: p.name for p in service.list_products(workspace_id, limit=500)}
    return [
        EdgeSuggestionOut(
            id=s.id,
            source_product_id=s.source_product_id,
            source_product_name=all_prods.get(s.source_product_id, "Unknown"),
            target_product_id=s.target_product_id,
            target_product_name=all_prods.get(s.target_product_id, "Unknown"),
            relation_type=s.relation_type,
            evidence=s.evidence,
            confidence=s.confidence,
            document_id=s.document_id,
            document_filename=s.document.original_filename if s.document else None,
            status=s.status,
        )
        for s in suggestions
    ]


@router.post("/graph/auto-graph", response_model=AutoGraphOut)
def auto_graph(
    deps: tuple[CatalogService, uuid.UUID, uuid.UUID] = Depends(_get_service),
    db: Session = Depends(get_db),
) -> AutoGraphOut:
    """Propose solution-selling relationships from the listed products."""
    service, org_id, workspace_id = deps
    try:
        result = suggest_solution_graph(db, workspace_id=workspace_id, org_id=org_id)
    except ProviderRateLimited as exc:
        raise HTTPException(
            status_code=429,
            detail="The model is busy. Wait a moment and try Auto-graph again.",
        ) from exc
    except ProviderError as exc:
        raise HTTPException(
            status_code=503,
            detail="The model could not graph these products. Try again shortly.",
        ) from exc
    names = {p.id: p.name for p in service.list_products(workspace_id, limit=500)}
    edges = [
        EdgeSuggestionOut(
            id=edge.id,
            source_product_id=edge.source_product_id,
            source_product_name=names.get(edge.source_product_id, "Unknown"),
            target_product_id=edge.target_product_id,
            target_product_name=names.get(edge.target_product_id, "Unknown"),
            relation_type=edge.relation_type,
            evidence=edge.evidence,
            confidence=edge.confidence,
            document_id=edge.document_id,
            status=edge.status,
        )
        for edge in result.edges
    ]
    links = [
        ContextLinkOut(
            id=link.id,
            product_id=link.product_id,
            product_name=names.get(link.product_id, "Unknown"),
            context_id=link.context_id,
            context_name=link.context.name if link.context else "Unknown",
            context_kind=link.context.kind if link.context else "use_case",
            relation_type=link.relation_type,
            evidence=link.evidence,
            confidence=link.confidence,
            status=link.status,
            is_ai_suggested=link.is_ai_suggested,
        )
        for link in result.context_links
    ]
    return AutoGraphOut(edges=edges, context_links=links, proposed=result.proposed)


@router.post("/graph/edges/{edge_id}/approve", response_model=ProductEdgeOut)
def approve_edge(
    edge_id: uuid.UUID,
    deps: tuple[CatalogService, uuid.UUID, uuid.UUID] = Depends(_get_service),
) -> ProductEdgeOut:
    service, _, workspace_id = deps
    edge = service.approve_edge(edge_id, workspace_id)
    if not edge:
        raise HTTPException(status_code=404, detail="Edge not found")
    all_prods = {p.id: p.name for p in service.list_products(workspace_id, limit=500)}
    return ProductEdgeOut(
        id=edge.id,
        org_id=edge.org_id,
        workspace_id=edge.workspace_id,
        source_product_id=edge.source_product_id,
        source_product_name=all_prods.get(edge.source_product_id, "Unknown"),
        target_product_id=edge.target_product_id,
        target_product_name=all_prods.get(edge.target_product_id, "Unknown"),
        relation_type=edge.relation_type,
        evidence=edge.evidence,
        confidence=edge.confidence,
        document_id=edge.document_id,
        is_ai_suggested=edge.is_ai_suggested,
        status=edge.status,
        rejection_reason=edge.rejection_reason,
        created_at=edge.created_at,
    )


@router.post("/graph/edges/{edge_id}/reject", response_model=ProductEdgeOut)
def reject_edge(
    edge_id: uuid.UUID,
    payload: EdgeActionIn | None = None,
    deps: tuple[CatalogService, uuid.UUID, uuid.UUID] = Depends(_get_service),
) -> ProductEdgeOut:
    service, _, workspace_id = deps
    reason = payload.reason if payload else "Rejected by solutions engineer"
    edge = service.reject_edge(edge_id, workspace_id, reason)
    if not edge:
        raise HTTPException(status_code=404, detail="Edge not found")
    all_prods = {p.id: p.name for p in service.list_products(workspace_id, limit=500)}
    return ProductEdgeOut(
        id=edge.id,
        org_id=edge.org_id,
        workspace_id=edge.workspace_id,
        source_product_id=edge.source_product_id,
        source_product_name=all_prods.get(edge.source_product_id, "Unknown"),
        target_product_id=edge.target_product_id,
        target_product_name=all_prods.get(edge.target_product_id, "Unknown"),
        relation_type=edge.relation_type,
        evidence=edge.evidence,
        confidence=edge.confidence,
        document_id=edge.document_id,
        is_ai_suggested=edge.is_ai_suggested,
        status=edge.status,
        rejection_reason=edge.rejection_reason,
        created_at=edge.created_at,
    )


# ---------------------------------------------------------------------------
# Reference Architecture Endpoints
# ---------------------------------------------------------------------------


@router.get("/catalog/reference-architectures", response_model=list[ReferenceArchitectureOut])
def list_reference_architectures(
    deps: tuple[CatalogService, uuid.UUID, uuid.UUID] = Depends(_get_service),
) -> list[ReferenceArchitectureOut]:
    service, _, workspace_id = deps
    archs = service.list_reference_architectures(workspace_id)
    all_prods = {p.id: p for p in service.list_products(workspace_id, limit=500)}
    return [
        ReferenceArchitectureOut(
            id=a.id,
            org_id=a.org_id,
            workspace_id=a.workspace_id,
            name=a.name,
            slug=a.slug,
            description=a.description,
            architecture_overview=a.architecture_overview,
            target_segment=a.target_segment,
            created_at=a.created_at,
            products=[
                ReferenceArchitectureProductOut(
                    product_id=p_item.product_id,
                    product_name=all_prods[p_item.product_id].name if p_item.product_id in all_prods else "Unknown",
                    vendor=all_prods[p_item.product_id].vendor if p_item.product_id in all_prods else "",
                    ownership=all_prods[p_item.product_id].ownership if p_item.product_id in all_prods else "",
                    category=all_prods[p_item.product_id].category if p_item.product_id in all_prods else "",
                    role=p_item.role,
                    notes=p_item.notes,
                )
                for p_item in a.products
            ],
        )
        for a in archs
    ]


@router.post(
    "/catalog/reference-architectures",
    response_model=ReferenceArchitectureOut,
    status_code=status.HTTP_201_CREATED,
)
def create_reference_architecture(
    data: ReferenceArchitectureIn,
    deps: tuple[CatalogService, uuid.UUID, uuid.UUID] = Depends(_get_service),
) -> ReferenceArchitectureOut:
    service, org_id, workspace_id = deps
    arch = service.create_reference_architecture(org_id, workspace_id, data)
    all_prods = {p.id: p for p in service.list_products(workspace_id, limit=500)}
    return ReferenceArchitectureOut(
        id=arch.id,
        org_id=arch.org_id,
        workspace_id=arch.workspace_id,
        name=arch.name,
        slug=arch.slug,
        description=arch.description,
        architecture_overview=arch.architecture_overview,
        target_segment=arch.target_segment,
        created_at=arch.created_at,
        products=[
            ReferenceArchitectureProductOut(
                product_id=p_item.product_id,
                product_name=all_prods[p_item.product_id].name if p_item.product_id in all_prods else "Unknown",
                vendor=all_prods[p_item.product_id].vendor if p_item.product_id in all_prods else "",
                ownership=all_prods[p_item.product_id].ownership if p_item.product_id in all_prods else "",
                category=all_prods[p_item.product_id].category if p_item.product_id in all_prods else "",
                role=p_item.role,
                notes=p_item.notes,
            )
            for p_item in arch.products
        ],
    )


@router.get("/catalog/reference-architectures/{arch_id}", response_model=ReferenceArchitectureOut)
def get_reference_architecture(
    arch_id: uuid.UUID,
    deps: tuple[CatalogService, uuid.UUID, uuid.UUID] = Depends(_get_service),
) -> ReferenceArchitectureOut:
    service, _, workspace_id = deps
    arch = service.get_reference_architecture(arch_id, workspace_id)
    if not arch:
        raise HTTPException(status_code=404, detail="Reference architecture not found")
    all_prods = {p.id: p for p in service.list_products(workspace_id, limit=500)}
    return ReferenceArchitectureOut(
        id=arch.id,
        org_id=arch.org_id,
        workspace_id=arch.workspace_id,
        name=arch.name,
        slug=arch.slug,
        description=arch.description,
        architecture_overview=arch.architecture_overview,
        target_segment=arch.target_segment,
        created_at=arch.created_at,
        products=[
            ReferenceArchitectureProductOut(
                product_id=p_item.product_id,
                product_name=all_prods[p_item.product_id].name if p_item.product_id in all_prods else "Unknown",
                vendor=all_prods[p_item.product_id].vendor if p_item.product_id in all_prods else "",
                ownership=all_prods[p_item.product_id].ownership if p_item.product_id in all_prods else "",
                category=all_prods[p_item.product_id].category if p_item.product_id in all_prods else "",
                role=p_item.role,
                notes=p_item.notes,
            )
            for p_item in arch.products
        ],
    )


@router.delete("/catalog/reference-architectures/{arch_id}")
def delete_reference_architecture(
    arch_id: uuid.UUID,
    deps: tuple[CatalogService, uuid.UUID, uuid.UUID] = Depends(_get_service),
) -> dict[str, bool]:
    service, _, workspace_id = deps
    ok = service.delete_reference_architecture(arch_id, workspace_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Reference architecture not found")
    return {"deleted": True}


# ---------------------------------------------------------------------------
# Graph Visualizer, Neighborhood & Query Endpoints
# ---------------------------------------------------------------------------


@router.get("/graph/portfolio", response_model=PortfolioGraphOut)
def get_portfolio_graph(
    deps: tuple[CatalogService, uuid.UUID, uuid.UUID] = Depends(_get_service),
) -> PortfolioGraphOut:
    service, _, workspace_id = deps
    return service.get_portfolio(workspace_id)


@router.get("/graph/neighborhood/{product_id}", response_model=NeighborhoodOut)
def get_neighborhood(
    product_id: uuid.UUID,
    deps: tuple[CatalogService, uuid.UUID, uuid.UUID] = Depends(_get_service),
) -> NeighborhoodOut:
    service, _, workspace_id = deps
    try:
        return service.get_product_neighborhood(product_id, workspace_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.get("/graph/query", response_model=GraphQueryOut)
def query_graph_impact(
    product_id: uuid.UUID = Query(...),
    deps: tuple[CatalogService, uuid.UUID, uuid.UUID] = Depends(_get_service),
) -> GraphQueryOut:
    """Answers 'what does product X require and what does it break' without a human reading a datasheet."""
    service, _, workspace_id = deps
    try:
        return service.query_impact(product_id, workspace_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.get("/graph/integrity", response_model=IntegrityReportOut)
def audit_graph_integrity(
    deps: tuple[CatalogService, uuid.UUID, uuid.UUID] = Depends(_get_service),
) -> IntegrityReportOut:
    service, _, workspace_id = deps
    return service.audit_integrity(workspace_id)


@router.get("/graph/coverage", response_model=CoverageReportOut)
def audit_graph_coverage(
    deps: tuple[CatalogService, uuid.UUID, uuid.UUID] = Depends(_get_service),
) -> CoverageReportOut:
    service, org_id, workspace_id = deps
    return service.audit_coverage(workspace_id, org_id)


# ---------------------------------------------------------------------------
# Sample catalog (3.3)
# ---------------------------------------------------------------------------
#
# The product list starts empty. This endpoint exists for demos and for a first look
# at the screens, so it is off unless DEMO_SEED_CATALOG says otherwise, and everything
# it creates is stamped as sample material that retrieval will not answer from.


@router.get("/catalog/sample-available")
def sample_catalog_available() -> dict[str, Any]:
    return {"available": demo_catalog_enabled(), "reason": None if demo_catalog_enabled() else DISABLED_MESSAGE}


@router.post("/catalog/seed")
def seed_catalog(
    deps: tuple[CatalogService, uuid.UUID, uuid.UUID] = Depends(_get_service),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    _, org_id, workspace_id = deps
    if not demo_catalog_enabled():
        raise HTTPException(status_code=404, detail=DISABLED_MESSAGE)
    try:
        counts = seed_demo_catalog(db, org_id, workspace_id)
    except AppError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message) from exc
    return {"status": "seeded", "counts": counts}
