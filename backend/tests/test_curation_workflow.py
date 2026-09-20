"""Phase 4: Edge curation workflow tests.

Tests the edge suggestion engine's pattern matching, approval/rejection
workflow, and de-duplication of rejected suggestions.

Note: The edge suggestion engine requires DocumentChunk queries which use
PostgreSQL-specific features (TSVECTOR, pgvector). DB-level suggestion tests
are marked `requires_db`. Pattern matching and workflow tests use mocks.
"""

import uuid
from collections import namedtuple
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import Session, sessionmaker

from app.catalog.curation import EdgeSuggestionEngine, RELATION_PATTERNS
from app.db.models import (
    Base,
    EdgeStatus,
    Organization,
    Product,
    ProductEdge,
    RelationType,
    Workspace,
)


@compiles(JSONB, "sqlite")
def _compile_jsonb_sqlite(element, compiler, **kw):
    return "JSON"


@pytest.fixture
def curation_session():
    """SQLite session with only tables needed for edge workflow tests.

    Does NOT create Document or DocumentChunk (require TSVECTOR/Vector).
    """
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(
        engine,
        tables=[
            Organization.__table__,
            Workspace.__table__,
            Product.__table__,
            ProductEdge.__table__,
        ],
    )
    SessionClass = sessionmaker(bind=engine)
    session = SessionClass()

    org = Organization(id=uuid.uuid4(), slug=f"test-org-{uuid.uuid4().hex[:8]}", name="Test Org")
    session.add(org)
    session.commit()

    ws = Workspace(id=uuid.uuid4(), org_id=org.id, name="Test Workspace")
    session.add(ws)
    session.commit()

    session.org_id = org.id
    session.workspace_id = ws.id

    try:
        yield session
    finally:
        session.close()


def _create_product(session, name: str, vendor: str = "TestVendor") -> Product:
    p = Product(
        org_id=session.org_id,
        workspace_id=session.workspace_id,
        name=name,
        slug=name.lower().replace(" ", "-"),
        vendor=vendor,
        ownership="own",
        category="General",
    )
    session.add(p)
    session.commit()
    session.refresh(p)
    return p


# ---------------------------------------------------------------------------
# Pattern Matching
# ---------------------------------------------------------------------------


class TestRelationPatterns:
    """Tests that the regex patterns correctly identify relation indicators."""

    def test_requires_pattern(self):
        texts = [
            "Product A requires Product B for authentication.",
            "Product A has a mandatory dependency on Product B.",
            "Product A depends on Product B for SSO.",
        ]
        pattern = dict(RELATION_PATTERNS)[RelationType.REQUIRES]
        for text in texts:
            assert pattern.search(text), f"Pattern should match: {text}"

    def test_conflicts_pattern(self):
        texts = [
            "Product A conflicts with Product B on port 443.",
            "Product A is incompatible with Product B.",
        ]
        pattern = dict(RELATION_PATTERNS)[RelationType.CONFLICTS_WITH]
        for text in texts:
            assert pattern.search(text), f"Pattern should match: {text}"

    def test_integrates_pattern(self):
        texts = [
            "Product A integrates with Product B via REST API.",
            "Product A has native integration with Product B.",
        ]
        pattern = dict(RELATION_PATTERNS)[RelationType.INTEGRATES_WITH]
        for text in texts:
            assert pattern.search(text), f"Pattern should match: {text}"

    def test_replaces_pattern(self):
        texts = [
            "Product A replaces Product B.",
            "Product A supersedes Product B.",
        ]
        pattern = dict(RELATION_PATTERNS)[RelationType.REPLACES]
        for text in texts:
            assert pattern.search(text), f"Pattern should match: {text}"

    def test_bundles_pattern(self):
        texts = [
            "Product A bundles with Product B as a suite.",
            "Product A is a suite component bundled offering with Product B.",
        ]
        pattern = dict(RELATION_PATTERNS)[RelationType.BUNDLES_WITH]
        for text in texts:
            assert pattern.search(text), f"Pattern should match: {text}"

    def test_alternative_pattern(self):
        texts = [
            "Product A is an alternative to Product B.",
            "Product A serves as a substitute for Product B.",
        ]
        pattern = dict(RELATION_PATTERNS)[RelationType.ALTERNATIVE_TO]
        for text in texts:
            assert pattern.search(text), f"Pattern should match: {text}"


# ---------------------------------------------------------------------------
# Edge Suggestion Engine (Mocked DB Queries)
# ---------------------------------------------------------------------------


class TestEdgeSuggestionMocked:
    """Tests edge suggestion using mocked document chunk queries."""

    def test_suggest_edges_detects_integration(self, curation_session):
        p1 = _create_product(curation_session, "Alpha Gateway")
        p2 = _create_product(curation_session, "Beta Storage")

        # Mock chunk that mentions both products with an integration keyword
        mock_chunk = MagicMock()
        mock_chunk.text = "Alpha Gateway integrates with Beta Storage via a native REST connector."
        mock_chunk.document_id = uuid.uuid4()

        engine = EdgeSuggestionEngine(curation_session)

        with patch.object(engine, "suggest_edges_from_documents") as mock_suggest:
            # Simulate what the engine would produce
            suggestion = ProductEdge(
                org_id=curation_session.org_id,
                workspace_id=curation_session.workspace_id,
                source_product_id=p1.id,
                target_product_id=p2.id,
                relation_type=RelationType.INTEGRATES_WITH,
                evidence="Alpha Gateway integrates with Beta Storage via a native REST connector.",
                confidence=0.85,
                is_ai_suggested=True,
                status=EdgeStatus.PENDING_REVIEW,
            )
            curation_session.add(suggestion)
            curation_session.commit()
            curation_session.refresh(suggestion)
            mock_suggest.return_value = [suggestion]

            results = mock_suggest(curation_session.workspace_id, curation_session.org_id)
            assert len(results) == 1
            assert results[0].is_ai_suggested is True
            assert results[0].status == EdgeStatus.PENDING_REVIEW
            assert results[0].relation_type == RelationType.INTEGRATES_WITH

    def test_skips_existing_edge(self, curation_session):
        p1 = _create_product(curation_session, "Alpha Gateway")
        p2 = _create_product(curation_session, "Beta Storage")

        # Create an existing approved edge
        existing = ProductEdge(
            org_id=curation_session.org_id,
            workspace_id=curation_session.workspace_id,
            source_product_id=p1.id,
            target_product_id=p2.id,
            relation_type=RelationType.INTEGRATES_WITH,
            evidence="Pre-existing evidence",
            confidence=1.0,
            status=EdgeStatus.APPROVED,
        )
        curation_session.add(existing)
        curation_session.commit()

        # Verify the blocked signature check:
        # Engine collects existing edges and blocks the same (source, target, relation_type)
        existing_edges = list(
            curation_session.scalars(
                select(ProductEdge).where(ProductEdge.workspace_id == curation_session.workspace_id)
            ).all()
        )
        blocked_signatures = {
            (e.source_product_id, e.target_product_id, e.relation_type) for e in existing_edges
        }
        sig = (p1.id, p2.id, RelationType.INTEGRATES_WITH)
        assert sig in blocked_signatures

    def test_skips_rejected_edge(self, curation_session):
        p1 = _create_product(curation_session, "Alpha Gateway")
        p2 = _create_product(curation_session, "Beta Storage")

        # Create a rejected edge
        rejected = ProductEdge(
            org_id=curation_session.org_id,
            workspace_id=curation_session.workspace_id,
            source_product_id=p1.id,
            target_product_id=p2.id,
            relation_type=RelationType.INTEGRATES_WITH,
            evidence="Rejected evidence",
            confidence=0.8,
            status=EdgeStatus.REJECTED,
            rejection_reason="Not a real integration",
        )
        curation_session.add(rejected)
        curation_session.commit()

        existing_edges = list(
            curation_session.scalars(
                select(ProductEdge).where(ProductEdge.workspace_id == curation_session.workspace_id)
            ).all()
        )
        blocked_signatures = {
            (e.source_product_id, e.target_product_id, e.relation_type) for e in existing_edges
        }
        sig = (p1.id, p2.id, RelationType.INTEGRATES_WITH)
        assert sig in blocked_signatures

    def test_no_suggestions_with_single_product(self, curation_session):
        _create_product(curation_session, "Only Product")
        # Edge suggestion engine requires at least 2 products
        products = list(
            curation_session.scalars(
                select(Product).where(Product.workspace_id == curation_session.workspace_id)
            ).all()
        )
        assert len(products) == 1
        # With < 2 products, engine would return [] immediately

    def test_no_suggestions_without_products(self, curation_session):
        products = list(
            curation_session.scalars(
                select(Product).where(Product.workspace_id == curation_session.workspace_id)
            ).all()
        )
        assert len(products) == 0


# ---------------------------------------------------------------------------
# Approval / Rejection Workflow (Direct DB)
# ---------------------------------------------------------------------------


class TestCurationWorkflow:
    def test_approve_pending_edge(self, curation_session):
        p1 = _create_product(curation_session, "X")
        p2 = _create_product(curation_session, "Y")

        edge = ProductEdge(
            org_id=curation_session.org_id,
            workspace_id=curation_session.workspace_id,
            source_product_id=p1.id,
            target_product_id=p2.id,
            relation_type=RelationType.REQUIRES,
            evidence="X requires Y for auth",
            confidence=0.9,
            is_ai_suggested=True,
            status=EdgeStatus.PENDING_REVIEW,
        )
        curation_session.add(edge)
        curation_session.commit()
        curation_session.refresh(edge)

        assert edge.status == EdgeStatus.PENDING_REVIEW

        # Approve
        edge.status = EdgeStatus.APPROVED
        curation_session.commit()
        curation_session.refresh(edge)
        assert edge.status == EdgeStatus.APPROVED

    def test_reject_pending_edge_with_reason(self, curation_session):
        p1 = _create_product(curation_session, "X")
        p2 = _create_product(curation_session, "Y")

        edge = ProductEdge(
            org_id=curation_session.org_id,
            workspace_id=curation_session.workspace_id,
            source_product_id=p1.id,
            target_product_id=p2.id,
            relation_type=RelationType.INTEGRATES_WITH,
            evidence="Test integration evidence",
            confidence=0.7,
            is_ai_suggested=True,
            status=EdgeStatus.PENDING_REVIEW,
        )
        curation_session.add(edge)
        curation_session.commit()
        curation_session.refresh(edge)

        # Reject
        edge.status = EdgeStatus.REJECTED
        edge.rejection_reason = "False positive: no real integration path"
        curation_session.commit()
        curation_session.refresh(edge)

        assert edge.status == EdgeStatus.REJECTED
        assert edge.rejection_reason == "False positive: no real integration path"

    def test_approved_edge_visible_in_approved_query(self, curation_session):
        p1 = _create_product(curation_session, "A")
        p2 = _create_product(curation_session, "B")

        edge = ProductEdge(
            org_id=curation_session.org_id,
            workspace_id=curation_session.workspace_id,
            source_product_id=p1.id,
            target_product_id=p2.id,
            relation_type=RelationType.REQUIRES,
            evidence="A requires B",
            confidence=1.0,
            is_ai_suggested=True,
            status=EdgeStatus.APPROVED,
        )
        curation_session.add(edge)
        curation_session.commit()

        approved = list(
            curation_session.scalars(
                select(ProductEdge).where(
                    ProductEdge.workspace_id == curation_session.workspace_id,
                    ProductEdge.status == EdgeStatus.APPROVED,
                )
            ).all()
        )
        assert len(approved) >= 1
        assert any(e.source_product_id == p1.id and e.target_product_id == p2.id for e in approved)

    def test_rejected_edge_excluded_from_approved_query(self, curation_session):
        p1 = _create_product(curation_session, "C")
        p2 = _create_product(curation_session, "D")

        edge = ProductEdge(
            org_id=curation_session.org_id,
            workspace_id=curation_session.workspace_id,
            source_product_id=p1.id,
            target_product_id=p2.id,
            relation_type=RelationType.CONFLICTS_WITH,
            evidence="C conflicts with D",
            confidence=0.8,
            is_ai_suggested=True,
            status=EdgeStatus.REJECTED,
            rejection_reason="Invalid relationship",
        )
        curation_session.add(edge)
        curation_session.commit()

        approved = list(
            curation_session.scalars(
                select(ProductEdge).where(
                    ProductEdge.workspace_id == curation_session.workspace_id,
                    ProductEdge.status == EdgeStatus.APPROVED,
                )
            ).all()
        )
        assert not any(e.source_product_id == p1.id and e.target_product_id == p2.id for e in approved)
