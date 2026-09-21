"""3.1 Put what we read into the map, as suggestions only.

This is the persistence half of the read step. It resolves names against what is
already on the map, creates what is missing as ``suggested``, and files every
relationship as ``pending_review`` with its quote, page, and confidence.

Three rules keep it safe to run on every upload:

* nothing here ever approves anything; a person accepts, one at a time or in bulk;
* a pair that was already rejected is never proposed again unchanged, so the review
  queue does not refill itself with the same rejected claim;
* everything is scoped to the document's org and workspace, so one tenant's datasheet
  can never touch another tenant's map.

If the model read produced nothing, the old regex pass runs instead. It finds less,
but it finds it deterministically, which is what the offline test suite relies on.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.catalog import extraction as graph_extraction
from app.catalog.curation import EdgeSuggestionEngine
from app.core.config import settings
from app.core.logging import get_logger
from app.db.models import (
    CurationStatus,
    Document,
    DocumentChunk,
    EdgeStatus,
    Product,
    ProductContextLink,
    ProductEdge,
    RelationType,
    SellingContext,
)

logger = get_logger(__name__)

#: Relations that point at a use case / room type / platform rather than a product.
_CONTEXT_RELATIONS = ProductContextLink.CONTEXT_RELATIONS


@dataclass
class IngestSummary:
    """What one read added to the map. Plain counts, safe to show a salesperson."""

    products_created: int = 0
    contexts_created: int = 0
    edges_created: int = 0
    context_links_created: int = 0
    origin: str = "none"  # llm | regex | none
    skipped: list[str] = field(default_factory=list)

    @property
    def total_suggestions(self) -> int:
        return self.edges_created + self.context_links_created

    def as_dict(self) -> dict:
        return {
            "products_created": self.products_created,
            "contexts_created": self.contexts_created,
            "edges_created": self.edges_created,
            "context_links_created": self.context_links_created,
            "origin": self.origin,
            "skipped": list(self.skipped),
        }


class GraphIngestor:
    def __init__(self, db: Session):
        self.db = db

    # -- public ------------------------------------------------------------

    def ingest_document(self, document: Document, *, provider=None) -> IngestSummary:
        """Read one ready document and file suggestions against the map."""
        if document.org_id is None:
            return IngestSummary(skipped=["document has no organisation"])

        text = self._document_text(document)
        extracted = graph_extraction.GraphExtraction(origin="none")
        if settings.graph_extraction_enabled and text:
            extracted = graph_extraction.extract_graph(
                text, filename=document.original_filename, provider=provider
            )

        if extracted.is_empty:
            return self._regex_fallback(document)

        return self._persist(document, extracted)

    def accept_high_confidence(
        self,
        *,
        org_id: uuid.UUID,
        workspace_id: uuid.UUID,
        min_confidence: float | None = None,
        document_id: uuid.UUID | None = None,
    ) -> dict:
        """Accept every waiting suggestion we are confident about, in one go."""
        threshold = (
            settings.graph_auto_accept_confidence if min_confidence is None else min_confidence
        )

        edge_stmt = select(ProductEdge).where(
            ProductEdge.org_id == org_id,
            ProductEdge.workspace_id == workspace_id,
            ProductEdge.status == EdgeStatus.PENDING_REVIEW,
            ProductEdge.confidence >= threshold,
        )
        link_stmt = select(ProductContextLink).where(
            ProductContextLink.org_id == org_id,
            ProductContextLink.workspace_id == workspace_id,
            ProductContextLink.status == EdgeStatus.PENDING_REVIEW,
            ProductContextLink.confidence >= threshold,
        )
        if document_id is not None:
            edge_stmt = edge_stmt.where(ProductEdge.document_id == document_id)
            link_stmt = link_stmt.where(ProductContextLink.document_id == document_id)

        edges = list(self.db.scalars(edge_stmt).all())
        links = list(self.db.scalars(link_stmt).all())

        confirmed_products: set[uuid.UUID] = set()
        confirmed_contexts: set[uuid.UUID] = set()
        for edge in edges:
            edge.status = EdgeStatus.APPROVED
            confirmed_products.update({edge.source_product_id, edge.target_product_id})
        for link in links:
            link.status = EdgeStatus.APPROVED
            confirmed_products.add(link.product_id)
            confirmed_contexts.add(link.context_id)

        # Accepting a relationship means accepting both ends of it.
        products_confirmed = self._confirm(Product, confirmed_products)
        contexts_confirmed = self._confirm(SellingContext, confirmed_contexts)

        self.db.commit()
        return {
            "min_confidence": threshold,
            "relationships_accepted": len(edges),
            "context_links_accepted": len(links),
            "products_confirmed": products_confirmed,
            "contexts_confirmed": contexts_confirmed,
        }

    # -- reading -----------------------------------------------------------

    def _document_text(self, document: Document) -> str:
        chunks = list(
            self.db.scalars(
                select(DocumentChunk)
                .where(DocumentChunk.document_id == document.id)
                .order_by(DocumentChunk.chunk_index)
            ).all()
        )
        if not chunks:
            return ""
        budget = max(500, settings.graph_extract_max_chars)
        parts: list[str] = []
        total = 0
        for chunk in chunks:
            piece = chunk.text or ""
            if not piece:
                continue
            page = chunk.page_number
            header = f"[page {page}]\n" if page else ""
            parts.append(header + piece)
            total += len(piece) + len(header) + 2
            if total >= budget:
                break
        return "\n\n".join(parts)

    # -- writing -----------------------------------------------------------

    def _persist(
        self, document: Document, extracted: graph_extraction.GraphExtraction
    ) -> IngestSummary:
        summary = IngestSummary(origin=extracted.origin)
        org_id = document.org_id
        workspace_id = document.workspace_id

        products = self._product_index(workspace_id)
        contexts = self._context_index(workspace_id)
        blocked_edges = self._blocked_edges(workspace_id)
        blocked_links = self._blocked_links(workspace_id)
        taken_slugs = self._taken_slugs(workspace_id)

        nodes_by_key = {node.key: node for node in extracted.nodes}

        for relation in extracted.relations:
            source_key = graph_extraction.normalize_name(relation.source)
            target_key = graph_extraction.normalize_name(relation.target)
            source_node = nodes_by_key.get(source_key)
            target_node = nodes_by_key.get(target_key)
            if source_node is None or target_node is None:
                summary.skipped.append(f"{relation.source} -> {relation.target}: unnamed end")
                continue

            source_product = self._resolve_product(
                source_node, document, products, taken_slugs, summary
            )
            if source_product is None:
                continue

            wants_context = (
                relation.relation_type in _CONTEXT_RELATIONS and target_node.kind != "product"
            ) or target_node.kind in {"use_case", "room_type", "platform"}

            if wants_context and relation.relation_type in _CONTEXT_RELATIONS:
                context = self._resolve_context(
                    target_node, document, contexts, taken_slugs, summary
                )
                if context is None:
                    continue
                signature = (source_product.id, context.id, relation.relation_type)
                if signature in blocked_links:
                    continue
                self.db.add(
                    ProductContextLink(
                        org_id=org_id,
                        workspace_id=workspace_id,
                        product_id=source_product.id,
                        context_id=context.id,
                        relation_type=relation.relation_type,
                        evidence=self._evidence(relation, source_node.name, target_node.name),
                        confidence=relation.confidence,
                        document_id=document.id,
                        page_number=relation.page,
                        is_ai_suggested=True,
                        status=EdgeStatus.PENDING_REVIEW,
                    )
                )
                blocked_links.add(signature)
                summary.context_links_created += 1
                continue

            if target_node.kind != "product":
                # A product-to-product relation aimed at a use case is a misread.
                summary.skipped.append(
                    f"{relation.source} -> {relation.target}: "
                    f"{RelationType.words(relation.relation_type)} needs two products"
                )
                continue

            target_product = self._resolve_product(
                target_node, document, products, taken_slugs, summary
            )
            if target_product is None or target_product.id == source_product.id:
                continue

            signature = (source_product.id, target_product.id, relation.relation_type)
            if signature in blocked_edges:
                continue
            self.db.add(
                ProductEdge(
                    org_id=org_id,
                    workspace_id=workspace_id,
                    source_product_id=source_product.id,
                    target_product_id=target_product.id,
                    relation_type=relation.relation_type,
                    evidence=self._evidence(relation, source_node.name, target_node.name),
                    confidence=relation.confidence,
                    document_id=document.id,
                    page_number=relation.page,
                    is_ai_suggested=True,
                    status=EdgeStatus.PENDING_REVIEW,
                )
            )
            blocked_edges.add(signature)
            summary.edges_created += 1

        # Products named on their own are still worth proposing: they are what the
        # "import my product list" screen would otherwise have to be typed into.
        for node in extracted.nodes:
            if node.kind != "product":
                continue
            self._resolve_product(node, document, products, taken_slugs, summary)

        self.db.commit()
        logger.info(
            "map read for document %s: %s products, %s relationships, %s context links",
            document.id,
            summary.products_created,
            summary.edges_created,
            summary.context_links_created,
        )
        return summary

    def _regex_fallback(self, document: Document) -> IngestSummary:
        try:
            suggestions = EdgeSuggestionEngine(self.db).suggest_edges_from_documents(
                workspace_id=document.workspace_id,
                org_id=document.org_id,
                document_ids=[document.id],
            )
        except Exception:  # noqa: BLE001 - suggestions never fail an upload
            logger.warning("map read: regex pass failed for %s", document.id, exc_info=True)
            return IngestSummary(origin="none", skipped=["could not read relationships"])
        return IngestSummary(origin="regex", edges_created=len(suggestions))

    # -- resolution --------------------------------------------------------

    def _product_index(self, workspace_id: uuid.UUID) -> dict[str, Product]:
        index: dict[str, Product] = {}
        for product in self.db.scalars(
            select(Product).where(Product.workspace_id == workspace_id)
        ).all():
            for key in self._product_keys(product):
                index.setdefault(key, product)
        return index

    @staticmethod
    def _product_keys(product: Product) -> list[str]:
        keys = [graph_extraction.normalize_name(product.name)]
        if product.slug:
            keys.append(graph_extraction.normalize_name(product.slug.replace("-", " ")))
        for alias in product.aliases or []:
            keys.append(graph_extraction.normalize_name(str(alias)))
        return [key for key in keys if key]

    def _context_index(self, workspace_id: uuid.UUID) -> dict[tuple[str, str], SellingContext]:
        index: dict[tuple[str, str], SellingContext] = {}
        for context in self.db.scalars(
            select(SellingContext).where(SellingContext.workspace_id == workspace_id)
        ).all():
            keys = [graph_extraction.normalize_name(context.name)]
            for alias in context.aliases or []:
                keys.append(graph_extraction.normalize_name(str(alias)))
            for key in keys:
                if key:
                    index.setdefault((context.kind, key), context)
        return index

    def _blocked_edges(self, workspace_id: uuid.UUID) -> set[tuple]:
        return {
            (edge.source_product_id, edge.target_product_id, edge.relation_type)
            for edge in self.db.scalars(
                select(ProductEdge).where(ProductEdge.workspace_id == workspace_id)
            ).all()
        }

    def _blocked_links(self, workspace_id: uuid.UUID) -> set[tuple]:
        return {
            (link.product_id, link.context_id, link.relation_type)
            for link in self.db.scalars(
                select(ProductContextLink).where(
                    ProductContextLink.workspace_id == workspace_id
                )
            ).all()
        }

    def _taken_slugs(self, workspace_id: uuid.UUID) -> set[str]:
        product_slugs = set(
            self.db.scalars(
                select(Product.slug).where(Product.workspace_id == workspace_id)
            ).all()
        )
        context_slugs = set(
            self.db.scalars(
                select(SellingContext.slug).where(SellingContext.workspace_id == workspace_id)
            ).all()
        )
        return product_slugs | context_slugs

    def _unique_slug(self, name: str, taken: set[str]) -> str:
        base = graph_extraction.slugify(name)
        slug = base
        counter = 2
        while slug in taken:
            slug = f"{base}-{counter}"[:128]
            counter += 1
        taken.add(slug)
        return slug

    def _resolve_product(
        self,
        node: graph_extraction.ExtractedNode,
        document: Document,
        index: dict[str, Product],
        taken_slugs: set[str],
        summary: IngestSummary,
    ) -> Product | None:
        key = node.key
        if not key:
            return None
        found = index.get(key)
        if found is not None:
            self._enrich_product(found, node)
            return found

        product = Product(
            org_id=document.org_id,
            workspace_id=document.workspace_id,
            name=node.name[:512],
            slug=self._unique_slug(node.name, taken_slugs),
            vendor=(node.vendor or document.vendor or "Unspecified")[:255],
            category=node.category[:128],
            description=node.quote[:2000] or None,
            aliases=node.aliases or None,
            curation_status=CurationStatus.SUGGESTED,
            is_ai_suggested=True,
            source_document_id=document.id,
            collateral_document_ids=[str(document.id)],
        )
        self.db.add(product)
        self.db.flush()
        for alias_key in self._product_keys(product):
            index.setdefault(alias_key, product)
        index[key] = product
        summary.products_created += 1
        return product

    @staticmethod
    def _enrich_product(product: Product, node: graph_extraction.ExtractedNode) -> None:
        """Fill blanks on a product we already knew about. Never overwrites a person."""
        if node.aliases:
            existing = list(product.aliases or [])
            lowered = {str(item).lower() for item in existing}
            added = [alias for alias in node.aliases if alias.lower() not in lowered]
            if added:
                product.aliases = existing + added

    def _resolve_context(
        self,
        node: graph_extraction.ExtractedNode,
        document: Document,
        index: dict[tuple[str, str], SellingContext],
        taken_slugs: set[str],
        summary: IngestSummary,
    ) -> SellingContext | None:
        key = node.key
        if not key:
            return None
        kind = node.kind if node.kind != "product" else "use_case"
        found = index.get((kind, key))
        if found is not None:
            return found

        context = SellingContext(
            org_id=document.org_id,
            workspace_id=document.workspace_id,
            kind=kind,
            name=node.name[:255],
            slug=self._unique_slug(node.name, taken_slugs),
            description=node.quote[:2000] or None,
            aliases=node.aliases or None,
            curation_status=CurationStatus.SUGGESTED,
            is_ai_suggested=True,
            source_document_id=document.id,
        )
        self.db.add(context)
        self.db.flush()
        index[(kind, key)] = context
        summary.contexts_created += 1
        return context

    def _confirm(self, model, ids: set[uuid.UUID]) -> int:
        if not ids:
            return 0
        confirmed = 0
        for row in self.db.scalars(select(model).where(model.id.in_(ids))).all():
            if row.curation_status != CurationStatus.CONFIRMED:
                row.curation_status = CurationStatus.CONFIRMED
                confirmed += 1
        return confirmed

    @staticmethod
    def _evidence(
        relation: graph_extraction.ExtractedRelation, source_name: str, target_name: str
    ) -> str:
        quote = (relation.quote or "").strip()
        words = RelationType.words(relation.relation_type)
        claim = f"{source_name} {words} {target_name}."
        if not quote:
            return claim
        if len(quote) < 15:
            return f"{claim} From the source: \u201c{quote}\u201d"
        return quote[:4000]
