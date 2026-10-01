from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import delete, func, or_, select
from sqlalchemy.orm import Session, selectinload

from app.catalog.graph import (
    build_portfolio_graph,
    compute_coverage,
    get_neighborhood,
    query_product_impact,
    run_integrity_check,
)
from app.catalog.models import (
    CapabilityIn,
    CoverageReportOut,
    GraphQueryOut,
    IntegrityReportOut,
    NeighborhoodOut,
    PortfolioGraphOut,
    ProductCapabilityIn,
    ProductEdgeIn,
    ProductEdgeUpdate,
    ProductIn,
    ProductUpdate,
    ReferenceArchitectureIn,
    slugify,
)
from app.core.errors import AppError
from app.db.models import (
    Capability,
    Document,
    EdgeStatus,
    Ownership,
    Product,
    ProductCapability,
    ProductEdge,
    ReferenceArchitecture,
    ReferenceArchitectureProduct,
)


class CatalogService:
    def __init__(self, db: Session):
        self.db = db

    def _validate_collateral(self, org_id, workspace_id, ids):
        expected = {uuid.UUID(str(value)) for value in (ids or [])}
        if not expected:
            return
        found = set(self.db.scalars(select(Document.id).where(Document.id.in_(expected), Document.org_id == org_id, Document.workspace_id == workspace_id)))
        if found != expected:
            raise AppError("collateral document not found", status_code=404)

    # -----------------------------------------------------------------------
    # Products
    # -----------------------------------------------------------------------

    def create_product(
        self,
        org_id: uuid.UUID,
        workspace_id: uuid.UUID,
        data: ProductIn,
    ) -> Product:
        self._validate_collateral(org_id, workspace_id, data.collateral_document_ids)
        slug = data.slug or slugify(data.name)
        if not slug:
            slug = f"prod-{uuid.uuid4().hex[:8]}"

        existing = self.db.scalar(
            select(Product).where(Product.workspace_id == workspace_id, Product.slug == slug)
        )
        if existing:
            slug = f"{slug}-{uuid.uuid4().hex[:4]}"

        # Validate resold product fields
        if data.ownership == Ownership.RESOLD:
            if not data.vendor or data.vendor.lower() in ("own", "in-house", "internal"):
                raise AppError(
                    status_code=400,
                    code="invalid_resold_vendor",
                    message="Resold product must specify a valid third-party vendor name",
                )

        product = Product(
            org_id=org_id,
            workspace_id=workspace_id,
            name=data.name,
            slug=slug,
            vendor=data.vendor,
            ownership=data.ownership,
            category=data.category,
            tier=data.tier,
            deployment_model=data.deployment_model,
            licensing_model=data.licensing_model,
            target_segment=data.target_segment,
            lifecycle_status=data.lifecycle_status,
            prerequisites=data.prerequisites,
            support_path=data.support_path,
            description=data.description,
            collateral_document_ids=[str(doc_id) for doc_id in data.collateral_document_ids]
            if data.collateral_document_ids
            else [],
            partner_tier=data.partner_tier,
            margin_band=data.margin_band,
            support_owner=data.support_owner,
            contract_constraints=data.contract_constraints,
            source_of_truth_url=data.source_of_truth_url,
        )
        self.db.add(product)
        self.db.commit()
        self.db.refresh(product)
        return product

    def get_product(
        self, product_id: uuid.UUID, workspace_id: uuid.UUID
    ) -> Product | None:
        stmt = (
            select(Product)
            .options(
                selectinload(Product.capabilities).selectinload(ProductCapability.capability),
                selectinload(Product.outgoing_edges),
                selectinload(Product.incoming_edges),
                selectinload(Product.reference_architectures).selectinload(
                    ReferenceArchitectureProduct.architecture
                ),
            )
            .where(Product.id == product_id, Product.workspace_id == workspace_id)
        )
        return self.db.scalar(stmt)

    def list_products(
        self,
        workspace_id: uuid.UUID,
        vendor: str | None = None,
        ownership: str | None = None,
        category: str | None = None,
        lifecycle_status: str | None = None,
        search: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[Product]:
        stmt = (
            select(Product)
            .options(
                selectinload(Product.capabilities).selectinload(ProductCapability.capability),
            )
            .where(Product.workspace_id == workspace_id)
        )

        if vendor:
            stmt = stmt.where(Product.vendor.ilike(f"%{vendor}%"))
        if ownership:
            stmt = stmt.where(Product.ownership == ownership.lower())
        if category:
            stmt = stmt.where(Product.category.ilike(f"%{category}%"))
        if lifecycle_status:
            stmt = stmt.where(Product.lifecycle_status == lifecycle_status)
        if search:
            stmt = stmt.where(
                or_(
                    Product.name.ilike(f"%{search}%"),
                    Product.description.ilike(f"%{search}%"),
                    Product.vendor.ilike(f"%{search}%"),
                )
            )

        stmt = stmt.order_by(Product.name.asc()).limit(limit).offset(offset)
        return list(self.db.scalars(stmt).all())

    def update_product(
        self,
        product_id: uuid.UUID,
        workspace_id: uuid.UUID,
        data: ProductUpdate,
    ) -> Product | None:
        product = self.get_product(product_id, workspace_id)
        if not product:
            return None

        update_dict = data.model_dump(exclude_unset=True)
        if "collateral_document_ids" in update_dict:
            self._validate_collateral(product.org_id, workspace_id, update_dict["collateral_document_ids"])
        if "slug" in update_dict and update_dict["slug"]:
            update_dict["slug"] = slugify(update_dict["slug"])
        if "collateral_document_ids" in update_dict and update_dict["collateral_document_ids"] is not None:
            update_dict["collateral_document_ids"] = [
                str(d) for d in update_dict["collateral_document_ids"]
            ]

        for k, v in update_dict.items():
            setattr(product, k, v)

        self.db.commit()
        self.db.refresh(product)
        return product

    def delete_product(self, product_id: uuid.UUID, workspace_id: uuid.UUID) -> bool:
        product = self.get_product(product_id, workspace_id)
        if not product:
            return False
        self.db.delete(product)
        self.db.commit()
        return True

    # -----------------------------------------------------------------------
    # Capabilities
    # -----------------------------------------------------------------------

    def create_capability(self, org_id: uuid.UUID, data: CapabilityIn) -> Capability:
        slug = data.slug or slugify(data.name)
        if not slug:
            slug = f"cap-{uuid.uuid4().hex[:8]}"

        existing = self.db.scalar(
            select(Capability).where(Capability.org_id == org_id, Capability.slug == slug)
        )
        if existing:
            return existing

        capability = Capability(
            org_id=org_id,
            name=data.name,
            slug=slug,
            category=data.category,
            description=data.description,
        )
        self.db.add(capability)
        self.db.commit()
        self.db.refresh(capability)
        return capability

    def list_capabilities(
        self, org_id: uuid.UUID, category: str | None = None, limit: int = 100, offset: int = 0
    ) -> list[Capability]:
        stmt = (
            select(Capability)
            .options(selectinload(Capability.products))
            .where(Capability.org_id == org_id)
        )
        if category:
            stmt = stmt.where(Capability.category.ilike(f"%{category}%"))
        stmt = stmt.order_by(Capability.category.asc(), Capability.name.asc())
        return list(self.db.scalars(stmt.limit(max(1, min(limit, 500))).offset(max(0, offset))).all())

    def get_capability(self, capability_id: uuid.UUID, org_id: uuid.UUID) -> Capability | None:
        stmt = (
            select(Capability)
            .options(selectinload(Capability.products))
            .where(Capability.id == capability_id, Capability.org_id == org_id)
        )
        return self.db.scalar(stmt)

    def assign_capability_to_product(
        self,
        product_id: uuid.UUID,
        workspace_id: uuid.UUID,
        data: ProductCapabilityIn,
    ) -> ProductCapability:
        product = self.get_product(product_id, workspace_id)
        if not product:
            raise AppError(status_code=404, code="not_found", message=f"Product {product_id} not found")

        capability = self.db.scalar(select(Capability).where(Capability.id == data.capability_id))
        if not capability:
            raise AppError(status_code=404, code="not_found", message=f"Capability {data.capability_id} not found")

        existing = self.db.scalar(
            select(ProductCapability).where(
                ProductCapability.product_id == product_id,
                ProductCapability.capability_id == data.capability_id,
            )
        )
        if existing:
            existing.proficiency = data.proficiency
            existing.notes = data.notes
            self.db.commit()
            self.db.refresh(existing)
            return existing

        pc = ProductCapability(
            product_id=product_id,
            capability_id=data.capability_id,
            proficiency=data.proficiency,
            notes=data.notes,
        )
        self.db.add(pc)
        self.db.commit()
        self.db.refresh(pc)
        return pc

    def remove_capability_from_product(
        self,
        product_id: uuid.UUID,
        capability_id: uuid.UUID,
        workspace_id: uuid.UUID,
    ) -> bool:
        product = self.get_product(product_id, workspace_id)
        if not product:
            return False

        res = self.db.execute(
            delete(ProductCapability).where(
                ProductCapability.product_id == product_id,
                ProductCapability.capability_id == capability_id,
            )
        )
        self.db.commit()
        return res.rowcount > 0

    # -----------------------------------------------------------------------
    # Product Edges
    # -----------------------------------------------------------------------

    def create_edge(
        self,
        org_id: uuid.UUID,
        workspace_id: uuid.UUID,
        data: ProductEdgeIn,
    ) -> ProductEdge:
        if data.source_product_id == data.target_product_id:
            raise AppError(
                status_code=400,
                code="self_referential_edge",
                message="A product cannot have a graph relationship with itself",
            )

        if not data.evidence or not data.evidence.strip():
            raise AppError(
                status_code=400,
                code="missing_evidence",
                message="No edge without evidence: an edge must have non-empty supporting evidence text",
            )

        # Check product existence
        p_src = self.get_product(data.source_product_id, workspace_id)
        p_tgt = self.get_product(data.target_product_id, workspace_id)
        if not p_src or not p_tgt:
            raise AppError(
                status_code=404,
                code="product_not_found",
                message="Both source and target products must exist in workspace",
            )

        # Check for existing edge
        existing = self.db.scalar(
            select(ProductEdge).where(
                ProductEdge.source_product_id == data.source_product_id,
                ProductEdge.target_product_id == data.target_product_id,
                ProductEdge.relation_type == data.relation_type,
            )
        )
        if existing:
            existing.evidence = data.evidence
            existing.confidence = data.confidence
            existing.document_id = data.document_id
            existing.status = data.status
            self.db.commit()
            self.db.refresh(existing)
            return existing

        edge = ProductEdge(
            org_id=org_id,
            workspace_id=workspace_id,
            source_product_id=data.source_product_id,
            target_product_id=data.target_product_id,
            relation_type=data.relation_type,
            evidence=data.evidence,
            confidence=data.confidence,
            document_id=data.document_id,
            is_ai_suggested=data.is_ai_suggested,
            status=data.status,
        )
        self.db.add(edge)
        self.db.commit()
        self.db.refresh(edge)
        return edge

    def get_edge(self, edge_id: uuid.UUID, workspace_id: uuid.UUID) -> ProductEdge | None:
        stmt = (
            select(ProductEdge)
            .options(
                selectinload(ProductEdge.source_product),
                selectinload(ProductEdge.target_product),
                selectinload(ProductEdge.document),
            )
            .where(ProductEdge.id == edge_id, ProductEdge.workspace_id == workspace_id)
        )
        return self.db.scalar(stmt)

    def list_edges(
        self,
        workspace_id: uuid.UUID,
        status: str | None = None,
        relation_type: str | None = None,
        product_id: uuid.UUID | None = None,
        limit: int = 100, offset: int = 0,
    ) -> list[ProductEdge]:
        stmt = (
            select(ProductEdge)
            .options(
                selectinload(ProductEdge.source_product),
                selectinload(ProductEdge.target_product),
                selectinload(ProductEdge.document),
            )
            .where(ProductEdge.workspace_id == workspace_id)
        )

        if status:
            stmt = stmt.where(ProductEdge.status == status)
        if relation_type:
            stmt = stmt.where(ProductEdge.relation_type == relation_type)
        if product_id:
            stmt = stmt.where(
                or_(
                    ProductEdge.source_product_id == product_id,
                    ProductEdge.target_product_id == product_id,
                )
            )

        stmt = stmt.order_by(ProductEdge.created_at.desc())
        return list(self.db.scalars(stmt.limit(max(1, min(limit, 500))).offset(max(0, offset))).all())

    def update_edge(
        self,
        edge_id: uuid.UUID,
        workspace_id: uuid.UUID,
        data: ProductEdgeUpdate,
    ) -> ProductEdge | None:
        edge = self.get_edge(edge_id, workspace_id)
        if not edge:
            return None

        update_dict = data.model_dump(exclude_unset=True)
        for k, v in update_dict.items():
            setattr(edge, k, v)

        self.db.commit()
        self.db.refresh(edge)
        return edge

    def delete_edge(self, edge_id: uuid.UUID, workspace_id: uuid.UUID) -> bool:
        edge = self.get_edge(edge_id, workspace_id)
        if not edge:
            return False
        self.db.delete(edge)
        self.db.commit()
        return True

    def approve_edge(self, edge_id: uuid.UUID, workspace_id: uuid.UUID) -> ProductEdge | None:
        edge = self.get_edge(edge_id, workspace_id)
        if not edge:
            return None
        edge.status = EdgeStatus.APPROVED
        edge.rejection_reason = None
        self.db.commit()
        self.db.refresh(edge)
        return edge

    def reject_edge(
        self, edge_id: uuid.UUID, workspace_id: uuid.UUID, reason: str | None = None
    ) -> ProductEdge | None:
        edge = self.get_edge(edge_id, workspace_id)
        if not edge:
            return None
        edge.status = EdgeStatus.REJECTED
        edge.rejection_reason = reason or "Rejected by solutions engineer"
        self.db.commit()
        self.db.refresh(edge)
        return edge

    # -----------------------------------------------------------------------
    # Reference Architectures
    # -----------------------------------------------------------------------

    def create_reference_architecture(
        self,
        org_id: uuid.UUID,
        workspace_id: uuid.UUID,
        data: ReferenceArchitectureIn,
    ) -> ReferenceArchitecture:
        slug = data.slug or slugify(data.name)
        if not slug:
            slug = f"arch-{uuid.uuid4().hex[:8]}"

        arch = ReferenceArchitecture(
            org_id=org_id,
            workspace_id=workspace_id,
            name=data.name,
            slug=slug,
            description=data.description,
            architecture_overview=data.architecture_overview,
            target_segment=data.target_segment,
        )
        self.db.add(arch)
        self.db.flush()

        for item in data.products:
            rap = ReferenceArchitectureProduct(
                architecture_id=arch.id,
                product_id=item.product_id,
                role=item.role,
                notes=item.notes,
            )
            self.db.add(rap)

        self.db.commit()
        self.db.refresh(arch)
        return arch

    def list_reference_architectures(
        self, workspace_id: uuid.UUID, limit: int = 100, offset: int = 0
    ) -> list[ReferenceArchitecture]:
        stmt = (
            select(ReferenceArchitecture)
            .options(
                selectinload(ReferenceArchitecture.products).selectinload(
                    ReferenceArchitectureProduct.product
                )
            )
            .where(ReferenceArchitecture.workspace_id == workspace_id)
            .order_by(ReferenceArchitecture.name.asc())
        )
        return list(self.db.scalars(stmt.limit(max(1, min(limit, 500))).offset(max(0, offset))).all())

    def get_reference_architecture(
        self, arch_id: uuid.UUID, workspace_id: uuid.UUID
    ) -> ReferenceArchitecture | None:
        stmt = (
            select(ReferenceArchitecture)
            .options(
                selectinload(ReferenceArchitecture.products).selectinload(
                    ReferenceArchitectureProduct.product
                )
            )
            .where(
                ReferenceArchitecture.id == arch_id,
                ReferenceArchitecture.workspace_id == workspace_id,
            )
        )
        return self.db.scalar(stmt)

    def delete_reference_architecture(
        self, arch_id: uuid.UUID, workspace_id: uuid.UUID
    ) -> bool:
        arch = self.get_reference_architecture(arch_id, workspace_id)
        if not arch:
            return False
        self.db.delete(arch)
        self.db.commit()
        return True

    # -----------------------------------------------------------------------
    # Graph Analysis & Queries
    # -----------------------------------------------------------------------

    def get_portfolio(self, workspace_id: uuid.UUID) -> PortfolioGraphOut:
        products = self.list_products(workspace_id, limit=500)
        edges = self.list_edges(workspace_id, limit=500)
        return build_portfolio_graph(products, edges)

    def get_product_neighborhood(
        self, product_id: uuid.UUID, workspace_id: uuid.UUID
    ) -> NeighborhoodOut:
        products = self.list_products(workspace_id, limit=500)
        prods_by_id = {p.id: p for p in products}
        edges = self.list_edges(workspace_id, limit=500)
        archs = self.list_reference_architectures(workspace_id)
        return get_neighborhood(product_id, edges, prods_by_id, archs)

    def query_impact(
        self, product_id: uuid.UUID, workspace_id: uuid.UUID
    ) -> GraphQueryOut:
        products = self.list_products(workspace_id, limit=500)
        prods_by_id = {p.id: p for p in products}
        edges = self.list_edges(workspace_id, limit=500)
        archs = self.list_reference_architectures(workspace_id)
        return query_product_impact(product_id, edges, prods_by_id, archs)

    def audit_integrity(self, workspace_id: uuid.UUID) -> IntegrityReportOut:
        products = self.list_products(workspace_id, limit=500)
        prods_by_id = {p.id: p for p in products}
        edges = self.list_edges(workspace_id, limit=500)
        archs = self.list_reference_architectures(workspace_id)
        return run_integrity_check(edges, prods_by_id, archs)

    def audit_coverage(self, workspace_id: uuid.UUID, org_id: uuid.UUID) -> CoverageReportOut:
        products = self.list_products(workspace_id, limit=500)
        capabilities = self.list_capabilities(org_id, limit=500)
        edges = self.list_edges(workspace_id, limit=500)

        # Query documents referencing products
        docs = list(
            self.db.scalars(
                select(Document).where(
                    Document.workspace_id == workspace_id,
                    Document.org_id == org_id,
                    Document.is_current.is_(True),
                ).limit(2000)
            ).all()
        )
        docs_by_prod: dict[uuid.UUID, list[Document]] = {}
        for p in products:
            p_docs = []
            for d in docs:
                p_refs = d.products_referenced or []
                if p.name in p_refs or p.slug in p_refs or (p.collateral_document_ids and str(d.id) in p.collateral_document_ids):
                    p_docs.append(d)
            if p_docs:
                docs_by_prod[p.id] = p_docs

        return compute_coverage(products, capabilities, edges, docs_by_prod)
