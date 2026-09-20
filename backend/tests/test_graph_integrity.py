"""Phase 4: Graph integrity tests.

Tests cycle detection on `requires` edges, contradiction detection
(direct, bundle, transitive), and coverage report generation.
"""

import uuid
from collections import namedtuple
from datetime import datetime, timezone
from unittest.mock import MagicMock

import pytest

from app.catalog.graph import (
    compute_coverage,
    detect_contradictions,
    detect_cycles_in_requires,
    run_integrity_check,
)
from app.db.models import EdgeStatus, RelationType


def _mock_edge(
    source_id: uuid.UUID,
    target_id: uuid.UUID,
    relation_type: str,
    status: str = EdgeStatus.APPROVED,
) -> MagicMock:
    edge = MagicMock()
    edge.id = uuid.uuid4()
    edge.source_product_id = source_id
    edge.target_product_id = target_id
    edge.relation_type = relation_type
    edge.status = status
    edge.evidence = "Test evidence"
    edge.confidence = 1.0
    edge.document_id = None
    edge.is_ai_suggested = False
    edge.rejection_reason = None
    edge.created_at = datetime.now(timezone.utc)
    edge.org_id = uuid.uuid4()
    edge.workspace_id = uuid.uuid4()
    return edge


def _mock_product(product_id: uuid.UUID, name: str, vendor: str = "TestVendor") -> MagicMock:
    p = MagicMock()
    p.id = product_id
    p.name = name
    p.vendor = vendor
    p.ownership = "own"
    p.slug = name.lower().replace(" ", "-")
    p.category = "General"
    p.tier = "Core"
    p.deployment_model = "cloud"
    p.lifecycle_status = "GA"
    p.capabilities = []
    p.collateral_document_ids = None
    p.org_id = uuid.uuid4()
    p.workspace_id = uuid.uuid4()
    p.created_at = datetime.now(timezone.utc)
    p.updated_at = datetime.now(timezone.utc)
    return p


# ---------------------------------------------------------------------------
# Cycle Detection
# ---------------------------------------------------------------------------


class TestCycleDetection:
    def test_no_cycles_in_linear_chain(self):
        a, b, c = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
        edges = [
            _mock_edge(a, b, RelationType.REQUIRES),
            _mock_edge(b, c, RelationType.REQUIRES),
        ]
        cycles = detect_cycles_in_requires(edges)
        assert cycles == []

    def test_detects_two_node_cycle(self):
        a, b = uuid.uuid4(), uuid.uuid4()
        prods = {a: _mock_product(a, "A"), b: _mock_product(b, "B")}
        edges = [
            _mock_edge(a, b, RelationType.REQUIRES),
            _mock_edge(b, a, RelationType.REQUIRES),
        ]
        cycles = detect_cycles_in_requires(edges, prods)
        assert len(cycles) >= 1
        # At least one cycle contains both A and B
        flat = [name for cycle in cycles for name in cycle]
        assert "A" in flat and "B" in flat

    def test_detects_three_node_cycle(self):
        a, b, c = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
        prods = {
            a: _mock_product(a, "Alpha"),
            b: _mock_product(b, "Beta"),
            c: _mock_product(c, "Gamma"),
        }
        edges = [
            _mock_edge(a, b, RelationType.REQUIRES),
            _mock_edge(b, c, RelationType.REQUIRES),
            _mock_edge(c, a, RelationType.REQUIRES),
        ]
        cycles = detect_cycles_in_requires(edges, prods)
        assert len(cycles) >= 1

    def test_ignores_non_requires_edges(self):
        a, b = uuid.uuid4(), uuid.uuid4()
        edges = [
            _mock_edge(a, b, RelationType.INTEGRATES_WITH),
            _mock_edge(b, a, RelationType.INTEGRATES_WITH),
        ]
        cycles = detect_cycles_in_requires(edges)
        assert cycles == []

    def test_ignores_pending_edges(self):
        a, b = uuid.uuid4(), uuid.uuid4()
        edges = [
            _mock_edge(a, b, RelationType.REQUIRES, EdgeStatus.PENDING_REVIEW),
            _mock_edge(b, a, RelationType.REQUIRES, EdgeStatus.PENDING_REVIEW),
        ]
        cycles = detect_cycles_in_requires(edges)
        assert cycles == []


# ---------------------------------------------------------------------------
# Contradiction Detection
# ---------------------------------------------------------------------------


class TestContradictionDetection:
    def test_direct_requires_conflicts_contradiction(self):
        a, b = uuid.uuid4(), uuid.uuid4()
        prods = {a: _mock_product(a, "A"), b: _mock_product(b, "B")}
        edges = [
            _mock_edge(a, b, RelationType.REQUIRES),
            _mock_edge(a, b, RelationType.CONFLICTS_WITH),
        ]
        contradictions = detect_contradictions(edges, prods)
        assert len(contradictions) >= 1
        assert any(c["type"] == "direct_requires_conflict" for c in contradictions)

    def test_bundle_conflict_in_reference_architecture(self):
        a, b, c = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
        prods = {
            a: _mock_product(a, "A"),
            b: _mock_product(b, "B"),
            c: _mock_product(c, "C"),
        }
        # A conflicts with B
        edges = [_mock_edge(a, b, RelationType.CONFLICTS_WITH)]

        # A reference architecture containing both A and B
        ArchProduct = namedtuple("ArchProduct", ["product_id"])
        arch = MagicMock()
        arch.name = "Test Architecture"
        arch.products = [ArchProduct(product_id=a), ArchProduct(product_id=b), ArchProduct(product_id=c)]

        contradictions = detect_contradictions(edges, prods, reference_architectures=[arch])
        assert len(contradictions) >= 1
        assert any(c["type"] == "bundle_conflict" for c in contradictions)

    def test_transitive_requires_conflict(self):
        a, b, c = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
        prods = {
            a: _mock_product(a, "A"),
            b: _mock_product(b, "B"),
            c: _mock_product(c, "C"),
        }
        # A requires B, B requires C, but A conflicts_with C
        edges = [
            _mock_edge(a, b, RelationType.REQUIRES),
            _mock_edge(b, c, RelationType.REQUIRES),
            _mock_edge(a, c, RelationType.CONFLICTS_WITH),
        ]
        contradictions = detect_contradictions(edges, prods)
        # Should detect the direct A<>C contradiction at minimum
        assert len(contradictions) >= 1

    def test_no_contradictions_on_clean_graph(self):
        a, b, c = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
        prods = {
            a: _mock_product(a, "A"),
            b: _mock_product(b, "B"),
            c: _mock_product(c, "C"),
        }
        edges = [
            _mock_edge(a, b, RelationType.REQUIRES),
            _mock_edge(b, c, RelationType.INTEGRATES_WITH),
        ]
        contradictions = detect_contradictions(edges, prods)
        assert len(contradictions) == 0


# ---------------------------------------------------------------------------
# Integrity Report (Combined)
# ---------------------------------------------------------------------------


class TestIntegrityReport:
    def test_valid_graph_returns_is_valid_true(self):
        a, b = uuid.uuid4(), uuid.uuid4()
        prods = {a: _mock_product(a, "A"), b: _mock_product(b, "B")}
        edges = [_mock_edge(a, b, RelationType.INTEGRATES_WITH)]
        report = run_integrity_check(edges, prods)
        assert report.is_valid is True
        assert report.cycle_detected is False
        assert report.contradictions_detected is False

    def test_invalid_graph_with_cycle(self):
        a, b = uuid.uuid4(), uuid.uuid4()
        prods = {a: _mock_product(a, "A"), b: _mock_product(b, "B")}
        edges = [
            _mock_edge(a, b, RelationType.REQUIRES),
            _mock_edge(b, a, RelationType.REQUIRES),
        ]
        report = run_integrity_check(edges, prods)
        assert report.is_valid is False
        assert report.cycle_detected is True


# ---------------------------------------------------------------------------
# Coverage Report
# ---------------------------------------------------------------------------


class TestCoverageReport:
    def test_fully_covered_product(self):
        pid = uuid.uuid4()
        p = _mock_product(pid, "Full Product")
        cap = MagicMock()
        cap.id = uuid.uuid4()
        cap.capability_id = cap.id
        p.capabilities = [cap]
        p.collateral_document_ids = [str(uuid.uuid4())]

        other_pid = uuid.uuid4()
        other_p = _mock_product(other_pid, "Other")
        other_p.capabilities = [cap]
        other_p.collateral_document_ids = [str(uuid.uuid4())]

        edge = _mock_edge(pid, other_pid, RelationType.INTEGRATES_WITH)
        products = [p, other_p]
        edges = [edge]

        report = compute_coverage(products, [cap], edges)
        # Both products have caps, docs, edges
        assert report.products_with_edge == 2

    def test_product_missing_capabilities_detected(self):
        pid = uuid.uuid4()
        p = _mock_product(pid, "Naked Product")
        p.capabilities = []
        p.collateral_document_ids = None

        report = compute_coverage([p], [], [])
        assert report.products_with_capability == 0
        assert len(report.uncovered_products) == 1
        assert "capabilities" in report.uncovered_products[0].missing

    def test_orphan_capability_detected(self):
        pid = uuid.uuid4()
        p = _mock_product(pid, "Product")
        p.capabilities = []
        p.collateral_document_ids = None

        orphan_cap = MagicMock()
        orphan_cap.id = uuid.uuid4()
        orphan_cap.name = "Orphan Cap"
        orphan_cap.category = "Test"

        report = compute_coverage([p], [orphan_cap], [])
        assert len(report.orphan_capabilities) == 1
        assert report.orphan_capabilities[0]["name"] == "Orphan Cap"

    def test_empty_catalog_coverage(self):
        report = compute_coverage([], [], [])
        assert report.total_products == 0
        assert report.exit_criteria_met is False
