from __future__ import annotations

import re
import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import Document, DocumentChunk, EdgeStatus, Product, ProductEdge, RelationType

# Patterns mapping phrases to relationship types
RELATION_PATTERNS: list[tuple[str, re.Pattern]] = [
    (
        RelationType.REQUIRES,
        re.compile(r"(?i)\b(?:requires|prerequisite(?:\s+is)?|depends\s+on|mandatory\s+dependency)\b"),
    ),
    (
        RelationType.CONFLICTS_WITH,
        re.compile(r"(?i)\b(?:conflicts\s+with|incompatible\s+with|cannot\s+(?:run|coexist)\s+with|unsupported\s+alongside)\b"),
    ),
    (
        RelationType.INTEGRATES_WITH,
        re.compile(r"(?i)\b(?:integrates\s+with|native\s+integration|connects\s+to|federates\s+with|interoperable\s+with)\b"),
    ),
    (
        RelationType.REPLACES,
        re.compile(r"(?i)\b(?:replaces|supersedes|replaces\s+legacy|drop-in\s+replacement\s+for)\b"),
    ),
    (
        RelationType.BUNDLES_WITH,
        re.compile(r"(?i)\b(?:bundles\s+with|packaged\s+together|bundled\s+offering|suite\s+component)\b"),
    ),
    (
        RelationType.ALTERNATIVE_TO,
        re.compile(r"(?i)\b(?:alternative\s+to|drop-in\s+alternative|substitute\s+for|replaces\s+the\s+need\s+for)\b"),
    ),
    (
        RelationType.MIGRATES_TO,
        re.compile(r"(?i)\b(?:migrates\s+to|migration\s+path\s+to|upgrade\s+path\s+to)\b"),
    ),
]


class EdgeSuggestionEngine:
    def __init__(self, db: Session):
        self.db = db

    def suggest_edges_from_documents(
        self,
        workspace_id: uuid.UUID,
        org_id: uuid.UUID,
        document_ids: list[uuid.UUID] | None = None,
    ) -> list[ProductEdge]:
        """Scans document text for implied relationships between catalog products.

        Requirements from Project_Plan.md:
        - AI-suggested edges that you accept or reject.
        - Every suggestion cites the document implying it.
        - Accepted suggestions become edges; rejected ones do not reappear unchanged.
        """
        # 1. Fetch catalog products
        products = list(
            self.db.scalars(
                select(Product).where(Product.workspace_id == workspace_id)
            ).all()
        )
        if len(products) < 2:
            return []

        # 2. Fetch existing edges (to skip approved, pending, and rejected ones)
        existing_edges = list(
            self.db.scalars(
                select(ProductEdge).where(ProductEdge.workspace_id == workspace_id)
            ).all()
        )
        # Blocked signatures: (source_id, target_id, relation_type)
        blocked_signatures = {
            (e.source_product_id, e.target_product_id, e.relation_type)
            for e in existing_edges
        }

        # 3. Fetch chunks to scan
        stmt = (
            select(DocumentChunk)
            .join(Document, DocumentChunk.document_id == Document.id)
            .where(Document.workspace_id == workspace_id, Document.is_current.is_(True))
        )
        if document_ids:
            stmt = stmt.where(DocumentChunk.document_id.in_(document_ids))

        chunks = list(self.db.scalars(stmt).all())
        new_suggestions: list[ProductEdge] = []

        # Index product names and aliases for matching
        # (normalized name -> product)
        prod_lookup: list[tuple[str, Product]] = []
        for p in products:
            prod_lookup.append((p.name.lower(), p))
            if p.slug:
                prod_lookup.append((p.slug.lower().replace("-", " "), p))

        # Sort longer names first to avoid sub-phrase confusion
        prod_lookup.sort(key=lambda x: len(x[0]), reverse=True)

        for chunk in chunks:
            text = chunk.text
            lower_text = text.lower()

            # Find products mentioned in this chunk
            found_products: set[Product] = set()
            for name_str, prod in prod_lookup:
                if name_str in lower_text:
                    found_products.add(prod)

            if len(found_products) < 2:
                continue

            found_list = list(found_products)
            # Check pairwise relationships
            for i in range(len(found_list)):
                for j in range(len(found_list)):
                    if i == j:
                        continue
                    p1 = found_list[i]
                    p2 = found_list[j]

                    p1_name = p1.name.lower()
                    p2_name = p2.name.lower()

                    # Find sentences or windows containing both products
                    # Split chunk into sentences/clauses
                    sentences = re.split(r"(?<=[.!?\n])\s+", text)
                    for sent in sentences:
                        sent_lower = sent.lower()
                        if p1_name in sent_lower and p2_name in sent_lower:
                            # Test patterns
                            for rel_type, pattern in RELATION_PATTERNS:
                                match = pattern.search(sent)
                                if match:
                                    sig = (p1.id, p2.id, rel_type)
                                    if sig in blocked_signatures:
                                        continue

                                    # Extract evidence context
                                    evidence = sent.strip()
                                    if len(evidence) < 15:
                                        evidence = f"Document excerpt: '{sent.strip()}' indicates {p1.name} {rel_type} {p2.name}."

                                    confidence = 0.85
                                    if rel_type in (RelationType.REQUIRES, RelationType.CONFLICTS_WITH):
                                        confidence = 0.90

                                    suggestion = ProductEdge(
                                        org_id=org_id,
                                        workspace_id=workspace_id,
                                        source_product_id=p1.id,
                                        target_product_id=p2.id,
                                        relation_type=rel_type,
                                        evidence=evidence,
                                        confidence=confidence,
                                        document_id=chunk.document_id,
                                        is_ai_suggested=True,
                                        status=EdgeStatus.PENDING_REVIEW,
                                    )
                                    self.db.add(suggestion)
                                    blocked_signatures.add(sig)
                                    new_suggestions.append(suggestion)
                                    break  # matched a relation for this sentence

        if new_suggestions:
            self.db.commit()
            for s in new_suggestions:
                self.db.refresh(s)

        return new_suggestions
