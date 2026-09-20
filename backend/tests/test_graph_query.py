"""Phase 4: Graph query tests.

Tests the 'what does X require and what does it break' impact query,
neighborhood subgraph generation, and portfolio graph assembly.
"""

import uuid
from datetime import datetime, timezone
from unittest.mock import MagicMock

import pytest

from app.catalog.graph import (
    build_portfolio_graph,
    get_neighborhood,
    query_product_impact,
)
from app.db.models import EdgeStatus, RelationType


def _mock_edge(
    source_id: uuid.UUID,
    target_id: uuid.UUID,
    relation_type: str,
    status: str = EdgeStatus.APPROVED,
    evidence: str = "Test evidence",
) -> MagicMock:
    edge = MagicMock()
    edge.id = uuid.uuid4()
    edge.source_product_id = source_id
    edge.target_product_id = target_id
    edge.relation_type = relation_type
    edge.status = status
    edge.evidence = evidence
    edge.confidence = 1.0
    edge.document_id = None
    edge.is_ai_suggested = False
    edge.rejection_reason = None
    edge.created_at = datetime.now(timezone.utc)
    edge.org_id = uuid.uuid4()
    edge.workspace_id = uuid.uuid4()
    return edge


def _mock_product(
    product_id: uuid.UUID,
    name: str,
    vendor: str = "TestVendor",
    ownership: str = "own",
) -> MagicMock:
    p = MagicMock()
    p.id = product_id
    p.name = name
    p.vendor = vendor
    p.ownership = ownership
    p.slug = name.lower().replace(" ", "-")
    p.category = "General"
    p.tier = "Core"
    p.deployment_model = "cloud"
    p.licensing_model = "subscription"
    p.target_segment = "Enterprise"
    p.lifecycle_status = "GA"
    p.prerequisites = None
    p.support_path = None
    p.description = None
    p.capabilities = []
    p.collateral_document_ids = None
    p.partner_tier = None
    p.margin_band = None
    p.support_owner = None
    p.contract_constraints = None
    p.source_of_truth_url = None
    p.org_id = uuid.uuid4()
    p.workspace_id = uuid.uuid4()
    p.created_at = datetime.now(timezone.utc)
    p.updated_at = datetime.now(timezone.utc)
    return p


# ---------------------------------------------------------------------------
# Impact Query: "What does X require and what does it break?"
# ---------------------------------------------------------------------------


class TestImpactQuery:
    def test_direct_prerequisites(self):
        """A requires B, query A → B is listed as prerequisite."""
        a, b = uuid.uuid4(), uuid.uuid4()
        prods = {a: _mock_product(a, "A"), b: _mock_product(b, "B")}
        edges = [_mock_edge(a, b, RelationType.REQUIRES)]

        result = query_product_impact(a, edges, prods)
        assert result.product_name == "A"
        assert len(result.all_prerequisites) == 1
        assert result.all_prerequisites[0].name == "B"
        assert result.all_prerequisites[0].depth == 1

    def test_transitive_prerequisites(self):
        """A requires B, B requires C → query A yields B and C."""
        a, b, c = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
        prods = {
            a: _mock_product(a, "A"),
            b: _mock_product(b, "B"),
            c: _mock_product(c, "C"),
        }
        edges = [
            _mock_edge(a, b, RelationType.REQUIRES),
            _mock_edge(b, c, RelationType.REQUIRES),
        ]

        result = query_product_impact(a, edges, prods)
        prereq_names = {p.name for p in result.all_prerequisites}
        assert prereq_names == {"B", "C"}
        # C should be at depth 2
        c_item = [p for p in result.all_prerequisites if p.name == "C"][0]
        assert c_item.depth == 2

    def test_direct_conflicts(self):
        """A conflicts_with B → query A yields B as incompatibility."""
        a, b = uuid.uuid4(), uuid.uuid4()
        prods = {a: _mock_product(a, "A"), b: _mock_product(b, "B")}
        edges = [_mock_edge(a, b, RelationType.CONFLICTS_WITH)]

        result = query_product_impact(a, edges, prods)
        assert len(result.all_incompatibilities) == 1
        assert result.all_incompatibilities[0].conflicted_product_name == "B"

    def test_transitive_requirement_conflict(self):
        """A requires B, B conflicts_with C → query A yields C as indirect conflict."""
        a, b, c = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
        prods = {
            a: _mock_product(a, "A"),
            b: _mock_product(b, "B"),
            c: _mock_product(c, "C"),
        }
        edges = [
            _mock_edge(a, b, RelationType.REQUIRES),
            _mock_edge(b, c, RelationType.CONFLICTS_WITH),
        ]

        result = query_product_impact(a, edges, prods)
        conflict_names = {c.conflicted_product_name for c in result.all_incompatibilities}
        assert "C" in conflict_names

    def test_direct_integrations(self):
        """A integrates_with B → query A shows B as integration."""
        a, b = uuid.uuid4(), uuid.uuid4()
        prods = {a: _mock_product(a, "A"), b: _mock_product(b, "B")}
        edges = [_mock_edge(a, b, RelationType.INTEGRATES_WITH)]

        result = query_product_impact(a, edges, prods)
        assert len(result.direct_integrations) == 1
        assert result.direct_integrations[0].name == "B"

    def test_alternatives(self):
        """A alternative_to B → query A shows B as alternative."""
        a, b = uuid.uuid4(), uuid.uuid4()
        prods = {a: _mock_product(a, "A"), b: _mock_product(b, "B")}
        edges = [_mock_edge(a, b, RelationType.ALTERNATIVE_TO)]

        result = query_product_impact(a, edges, prods)
        assert len(result.alternatives) == 1
        assert result.alternatives[0].name == "B"

    def test_pending_edges_excluded(self):
        """Pending edges are excluded from impact computation."""
        a, b = uuid.uuid4(), uuid.uuid4()
        prods = {a: _mock_product(a, "A"), b: _mock_product(b, "B")}
        edges = [_mock_edge(a, b, RelationType.REQUIRES, EdgeStatus.PENDING_REVIEW)]

        result = query_product_impact(a, edges, prods)
        assert len(result.all_prerequisites) == 0

    def test_unknown_product_raises_valueerror(self):
        """Querying a product that doesn't exist raises ValueError."""
        fake_id = uuid.uuid4()
        with pytest.raises(ValueError, match="not found"):
            query_product_impact(fake_id, [], {})

    def test_no_edges_returns_empty_results(self):
        """Product with no edges returns empty prerequisites and conflicts."""
        a = uuid.uuid4()
        prods = {a: _mock_product(a, "Lonely")}
        result = query_product_impact(a, [], prods)
        assert result.all_prerequisites == []
        assert result.all_incompatibilities == []
        assert result.direct_integrations == []
        assert result.alternatives == []


# ---------------------------------------------------------------------------
# Neighborhood Subgraph
# ---------------------------------------------------------------------------


class TestNeighborhood:
    def test_neighborhood_includes_outgoing_requires(self):
        a, b = uuid.uuid4(), uuid.uuid4()
        prods = {a: _mock_product(a, "A"), b: _mock_product(b, "B")}
        edges = [_mock_edge(a, b, RelationType.REQUIRES)]

        nb = get_neighborhood(a, edges, prods)
        assert nb.center_product.name == "A"
        assert len(nb.upstream_requires) == 1
        assert nb.upstream_requires[0].target_product_name == "B"

    def test_neighborhood_includes_incoming_requires(self):
        a, b = uuid.uuid4(), uuid.uuid4()
        prods = {a: _mock_product(a, "A"), b: _mock_product(b, "B")}
        edges = [_mock_edge(b, a, RelationType.REQUIRES)]

        nb = get_neighborhood(a, edges, prods)
        assert len(nb.downstream_required_by) == 1

    def test_neighborhood_includes_conflicts(self):
        a, b = uuid.uuid4(), uuid.uuid4()
        prods = {a: _mock_product(a, "A"), b: _mock_product(b, "B")}
        edges = [_mock_edge(a, b, RelationType.CONFLICTS_WITH)]

        nb = get_neighborhood(a, edges, prods)
        assert len(nb.conflicts) == 1

    def test_neighborhood_includes_integrations(self):
        a, b = uuid.uuid4(), uuid.uuid4()
        prods = {a: _mock_product(a, "A"), b: _mock_product(b, "B")}
        edges = [_mock_edge(a, b, RelationType.INTEGRATES_WITH)]

        nb = get_neighborhood(a, edges, prods)
        assert len(nb.integrations) == 1

    def test_unknown_product_raises_valueerror(self):
        with pytest.raises(ValueError, match="not found"):
            get_neighborhood(uuid.uuid4(), [], {})


# ---------------------------------------------------------------------------
# Portfolio Graph Assembly
# ---------------------------------------------------------------------------


class TestPortfolioGraph:
    def test_builds_nodes_and_links(self):
        a, b = uuid.uuid4(), uuid.uuid4()
        pa = _mock_product(a, "Product A", vendor="VendorA")
        pb = _mock_product(b, "Product B", vendor="VendorB")
        edge = _mock_edge(a, b, RelationType.INTEGRATES_WITH)

        graph = build_portfolio_graph([pa, pb], [edge])
        assert len(graph.nodes) == 2
        assert len(graph.edges) == 1
        assert set(graph.vendors) == {"VendorA", "VendorB"}
        assert RelationType.INTEGRATES_WITH in graph.relation_types

    def test_empty_catalog_builds_empty_graph(self):
        graph = build_portfolio_graph([], [])
        assert graph.nodes == []
        assert graph.edges == []
        assert graph.categories == []
        assert graph.vendors == []

    def test_node_attributes_populated(self):
        pid = uuid.uuid4()
        p = _mock_product(pid, "Apex", vendor="Acme", ownership="own")
        p.category = "Identity"
        p.tier = "Premium"

        graph = build_portfolio_graph([p], [])
        node = graph.nodes[0]
        assert node.name == "Apex"
        assert node.vendor == "Acme"
        assert node.ownership == "own"
        assert node.category == "Identity"
        assert node.tier == "Premium"
