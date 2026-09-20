from __future__ import annotations

import uuid
from collections import defaultdict, deque
from typing import Any

from app.catalog.models import (
    ConflictItem,
    CoverageReportOut,
    GraphLink,
    GraphNode,
    GraphQueryOut,
    ImpactItem,
    IntegrityReportOut,
    NeighborhoodOut,
    PortfolioGraphOut,
    ProductCoverageDetail,
    ProductDetailOut,
    ProductEdgeOut,
    ProductOut,
    ReferenceArchitectureOut,
    ReferenceArchitectureProductOut,
)
from app.db.models import (
    Capability,
    EdgeStatus,
    Product,
    ProductEdge,
    ReferenceArchitecture,
    RelationType,
)


def detect_cycles_in_requires(
    edges: list[ProductEdge],
    products_by_id: dict[uuid.UUID, Product] | None = None,
) -> list[list[str]]:
    """Detect cycles in directed `requires` edges.

    An edge (A -> B) with relation_type='requires' means A requires B.
    A cycle means A requires B, B requires C, ..., and C requires A.
    """
    adj: dict[uuid.UUID, list[uuid.UUID]] = defaultdict(list)
    for edge in edges:
        if edge.relation_type == RelationType.REQUIRES and edge.status == EdgeStatus.APPROVED:
            adj[edge.source_product_id].append(edge.target_product_id)

    cycles: list[list[str]] = []
    visited: dict[uuid.UUID, int] = {}  # 0: unvisited, 1: visiting (in stack), 2: visited
    parent_path: list[uuid.UUID] = []

    def dfs(node: uuid.UUID) -> None:
        visited[node] = 1
        parent_path.append(node)
        for neighbor in adj.get(node, []):
            state = visited.get(neighbor, 0)
            if state == 1:
                # Cycle found!
                cycle_start_idx = parent_path.index(neighbor)
                cycle_nodes = parent_path[cycle_start_idx:] + [neighbor]
                if products_by_id:
                    cycle_names = [products_by_id[nid].name if nid in products_by_id else str(nid) for nid in cycle_nodes]
                else:
                    cycle_names = [str(nid) for nid in cycle_nodes]
                cycles.append(cycle_names)
            elif state == 0:
                dfs(neighbor)
        parent_path.pop()
        visited[node] = 2

    for start_node in list(adj.keys()):
        if visited.get(start_node, 0) == 0:
            dfs(start_node)

    return cycles


def detect_contradictions(
    edges: list[ProductEdge],
    products_by_id: dict[uuid.UUID, Product],
    reference_architectures: list[ReferenceArchitecture] | None = None,
) -> list[dict[str, Any]]:
    """Detect logical contradictions in the graph.

    Contradiction rules:
    1. Direct Contradiction: Product A `requires` B, but A `conflicts_with` B (or vice versa).
    2. Bundle/Reference Architecture Contradiction: A reference architecture contains products A and B,
       where A `conflicts_with` B.
    3. Transitive Requirement Conflict: A requires B, B requires C, but A `conflicts_with` C.
    """
    contradictions: list[dict[str, Any]] = []

    # Filter approved edges
    approved_edges = [e for e in edges if e.status == EdgeStatus.APPROVED]

    # Map pairs to relations
    edge_map: dict[tuple[uuid.UUID, uuid.UUID], set[str]] = defaultdict(set)
    conflict_pairs: set[frozenset[uuid.UUID]] = set()

    for e in approved_edges:
        edge_map[(e.source_product_id, e.target_product_id)].add(e.relation_type)
        if e.relation_type == RelationType.CONFLICTS_WITH:
            conflict_pairs.add(frozenset([e.source_product_id, e.target_product_id]))

    # Rule 1: Direct Contradiction (requires + conflicts_with on same pair)
    for (src, tgt), rtypes in edge_map.items():
        reverse_types = edge_map.get((tgt, src), set())
        has_requires = RelationType.REQUIRES in rtypes or RelationType.REQUIRES in reverse_types
        has_conflict = RelationType.CONFLICTS_WITH in rtypes or RelationType.CONFLICTS_WITH in reverse_types
        if has_requires and has_conflict:
            src_name = products_by_id.get(src).name if src in products_by_id else str(src)
            tgt_name = products_by_id.get(tgt).name if tgt in products_by_id else str(tgt)
            contradictions.append({
                "type": "direct_requires_conflict",
                "products": [src_name, tgt_name],
                "description": f"Product '{src_name}' and '{tgt_name}' have both 'requires' and 'conflicts_with' relationships declared.",
            })

    # Rule 2: Reference Architecture / Bundle Contradiction
    if reference_architectures:
        for arch in reference_architectures:
            arch_prod_ids = [rp.product_id for rp in arch.products]
            for i in range(len(arch_prod_ids)):
                for j in range(i + 1, len(arch_prod_ids)):
                    p1 = arch_prod_ids[i]
                    p2 = arch_prod_ids[j]
                    if frozenset([p1, p2]) in conflict_pairs:
                        p1_name = products_by_id.get(p1).name if p1 in products_by_id else str(p1)
                        p2_name = products_by_id.get(p2).name if p2 in products_by_id else str(p2)
                        contradictions.append({
                            "type": "bundle_conflict",
                            "architecture_name": arch.name,
                            "products": [p1_name, p2_name],
                            "description": f"Reference architecture '{arch.name}' includes mutually conflicting products '{p1_name}' and '{p2_name}'.",
                        })

    # Rule 3: Transitive Requirement Conflict
    # For every product, compute its requires closure. If any required component conflicts with the root or another required component:
    requires_adj: dict[uuid.UUID, list[uuid.UUID]] = defaultdict(list)
    for e in approved_edges:
        if e.relation_type == RelationType.REQUIRES:
            requires_adj[e.source_product_id].append(e.target_product_id)

    for root_id in products_by_id.keys():
        closure: set[uuid.UUID] = set()
        queue = deque([root_id])
        while queue:
            curr = queue.popleft()
            for nxt in requires_adj.get(curr, []):
                if nxt not in closure and nxt != root_id:
                    closure.add(nxt)
                    queue.append(nxt)

        for dep_id in closure:
            if frozenset([root_id, dep_id]) in conflict_pairs:
                root_name = products_by_id[root_id].name
                dep_name = products_by_id[dep_id].name
                # Avoid duplicate report if direct
                is_direct = (root_id, dep_id) in edge_map and RelationType.REQUIRES in edge_map[(root_id, dep_id)]
                if not is_direct:
                    contradictions.append({
                        "type": "transitive_requires_conflict",
                        "products": [root_name, dep_name],
                        "description": f"Product '{root_name}' transitively requires '{dep_name}', but is marked as conflicting with it.",
                    })

    return contradictions


def run_integrity_check(
    edges: list[ProductEdge],
    products_by_id: dict[uuid.UUID, Product],
    reference_architectures: list[ReferenceArchitecture] | None = None,
) -> IntegrityReportOut:
    """Full integrity audit: cycle detection and contradiction detection."""
    cycles = detect_cycles_in_requires(edges, products_by_id)
    contradictions = detect_contradictions(edges, products_by_id, reference_architectures)
    is_valid = (len(cycles) == 0) and (len(contradictions) == 0)
    return IntegrityReportOut(
        is_valid=is_valid,
        cycle_detected=len(cycles) > 0,
        cycles=cycles,
        contradictions_detected=len(contradictions) > 0,
        contradictions=contradictions,
    )


def compute_coverage(
    products: list[Product],
    capabilities: list[Capability],
    edges: list[ProductEdge],
    documents_by_product: dict[uuid.UUID, list[Any]] | None = None,
) -> CoverageReportOut:
    """Coverage report verifying every product has >= 1 capability, >= 1 document, and >= 1 edge."""
    docs_map = documents_by_product or {}
    total = len(products)
    if total == 0:
        return CoverageReportOut(
            total_products=0,
            products_with_capability=0,
            products_with_document=0,
            products_with_edge=0,
            fully_covered_products=0,
            coverage_percentage=100.0,
            orphan_capabilities=[],
            uncovered_products=[],
            exit_criteria_met=False,
        )

    # Track edge participation (approved or all)
    products_with_edges: set[uuid.UUID] = set()
    for e in edges:
        if e.status == EdgeStatus.APPROVED:
            products_with_edges.add(e.source_product_id)
            products_with_edges.add(e.target_product_id)

    # Track capability usage
    capabilities_used: set[uuid.UUID] = set()
    for p in products:
        for pc in p.capabilities:
            capabilities_used.add(pc.capability_id)

    orphan_caps: list[dict[str, Any]] = []
    for c in capabilities:
        if c.id not in capabilities_used:
            orphan_caps.append({
                "id": str(c.id),
                "name": c.name,
                "category": c.category,
            })

    with_cap = 0
    with_doc = 0
    with_edge = 0
    fully_covered = 0
    uncovered: list[ProductCoverageDetail] = []

    for p in products:
        has_cap = len(p.capabilities) > 0
        has_doc = (len(docs_map.get(p.id, [])) > 0) or (p.collateral_document_ids and len(p.collateral_document_ids) > 0)
        has_e = p.id in products_with_edges

        if has_cap:
            with_cap += 1
        if has_doc:
            with_doc += 1
        if has_e:
            with_edge += 1

        missing_items: list[str] = []
        if not has_cap:
            missing_items.append("capabilities")
        if not has_doc:
            missing_items.append("collateral_documents")
        if not has_e:
            missing_items.append("graph_edges")

        if not missing_items:
            fully_covered += 1
        else:
            uncovered.append(ProductCoverageDetail(
                id=p.id,
                name=p.name,
                vendor=p.vendor,
                ownership=p.ownership,
                missing=missing_items,
            ))

    cov_pct = round((fully_covered / total) * 100.0, 1) if total > 0 else 0.0
    exit_met = (fully_covered == total) and (len(orphan_caps) == 0) and (total >= 20)

    return CoverageReportOut(
        total_products=total,
        products_with_capability=with_cap,
        products_with_document=with_doc,
        products_with_edge=with_edge,
        fully_covered_products=fully_covered,
        coverage_percentage=cov_pct,
        orphan_capabilities=orphan_caps,
        uncovered_products=uncovered,
        exit_criteria_met=exit_met,
    )


def query_product_impact(
    product_id: uuid.UUID,
    edges: list[ProductEdge],
    products_by_id: dict[uuid.UUID, Product],
    reference_architectures: list[ReferenceArchitecture] | None = None,
) -> GraphQueryOut:
    """Answers 'what does X require and what does it break' without a human reading a datasheet.

    Computes:
    1. Transitive `requires` prerequisites with traversal path and depth.
    2. Complete incompatibilities:
       - Direct conflicts (X conflicts with Y, or Y conflicts with X)
       - Transitive requirement conflicts (a required dependency of X conflicts with Y)
       - Downstream conflicts (a product Z requires an item that conflicts with X)
    3. Direct integrations.
    4. Alternatives.
    5. Reference architectures composing this product.
    """
    if product_id not in products_by_id:
        raise ValueError(f"Product {product_id} not found in catalog")

    root_product = products_by_id[product_id]
    approved = [e for e in edges if e.status == EdgeStatus.APPROVED]

    # Graph adjacency by relation type
    requires_adj: dict[uuid.UUID, list[tuple[uuid.UUID, str]]] = defaultdict(list)
    required_by_adj: dict[uuid.UUID, list[tuple[uuid.UUID, str]]] = defaultdict(list)
    conflicts_adj: dict[uuid.UUID, list[tuple[uuid.UUID, str]]] = defaultdict(list)
    integrates_adj: dict[uuid.UUID, list[tuple[uuid.UUID, str]]] = defaultdict(list)
    alternative_adj: dict[uuid.UUID, list[tuple[uuid.UUID, str]]] = defaultdict(list)

    for e in approved:
        evidence = e.evidence
        if e.relation_type == RelationType.REQUIRES:
            requires_adj[e.source_product_id].append((e.target_product_id, evidence))
            required_by_adj[e.target_product_id].append((e.source_product_id, evidence))
        elif e.relation_type == RelationType.CONFLICTS_WITH:
            # Conflicts are symmetric in impact
            conflicts_adj[e.source_product_id].append((e.target_product_id, evidence))
            conflicts_adj[e.target_product_id].append((e.source_product_id, evidence))
        elif e.relation_type == RelationType.INTEGRATES_WITH:
            integrates_adj[e.source_product_id].append((e.target_product_id, evidence))
            integrates_adj[e.target_product_id].append((e.source_product_id, evidence))
        elif e.relation_type == RelationType.ALTERNATIVE_TO:
            alternative_adj[e.source_product_id].append((e.target_product_id, evidence))
            alternative_adj[e.target_product_id].append((e.source_product_id, evidence))

    # 1. Transitive Prerequisites (Requires closure)
    all_prerequisites: list[ImpactItem] = []
    seen_prereqs: set[uuid.UUID] = {product_id}
    # queue: (current_id, depth, path)
    q: deque[tuple[uuid.UUID, int, list[str]]] = deque([(product_id, 0, [root_product.name])])

    while q:
        curr_id, depth, path = q.popleft()
        for next_id, ev in requires_adj.get(curr_id, []):
            if next_id not in seen_prereqs:
                seen_prereqs.add(next_id)
                next_prod = products_by_id.get(next_id)
                next_name = next_prod.name if next_prod else str(next_id)
                new_path = path + [next_name]
                all_prerequisites.append(ImpactItem(
                    product_id=next_id,
                    name=next_name,
                    vendor=next_prod.vendor if next_prod else "Unknown",
                    ownership=next_prod.ownership if next_prod else "own",
                    depth=depth + 1,
                    path=new_path,
                    evidence=ev,
                ))
                q.append((next_id, depth + 1, new_path))

    # 2. Incompatibilities / What it breaks
    incompatibilities: list[ConflictItem] = []
    seen_conflicts: set[uuid.UUID] = set()

    # 2a. Direct conflicts of root product
    for c_id, ev in conflicts_adj.get(product_id, []):
        if c_id not in seen_conflicts and c_id != product_id:
            seen_conflicts.add(c_id)
            c_prod = products_by_id.get(c_id)
            incompatibilities.append(ConflictItem(
                conflicted_product_id=c_id,
                conflicted_product_name=c_prod.name if c_prod else str(c_id),
                conflicted_product_vendor=c_prod.vendor if c_prod else "Unknown",
                reason="Direct incompatibility with selected product",
                conflict_path=[root_product.name, c_prod.name if c_prod else str(c_id)],
                evidence=ev,
            ))

    # 2b. Transitive requirement conflicts: A required component of X conflicts with Y
    for prereq in all_prerequisites:
        for c_id, ev in conflicts_adj.get(prereq.product_id, []):
            if c_id not in seen_conflicts and c_id != product_id:
                seen_conflicts.add(c_id)
                c_prod = products_by_id.get(c_id)
                incompatibilities.append(ConflictItem(
                    conflicted_product_id=c_id,
                    conflicted_product_name=c_prod.name if c_prod else str(c_id),
                    conflicted_product_vendor=c_prod.vendor if c_prod else "Unknown",
                    reason=f"Required prerequisite '{prereq.name}' is incompatible with this product",
                    conflict_path=prereq.path + [c_prod.name if c_prod else str(c_id)],
                    evidence=ev,
                ))

    # 2c. Downstream dependency breaks: Product Z requires something that conflicts with X
    for c_id in list(seen_conflicts):
        for downstream_id, ev in required_by_adj.get(c_id, []):
            if downstream_id not in seen_conflicts and downstream_id != product_id:
                seen_conflicts.add(downstream_id)
                d_prod = products_by_id.get(downstream_id)
                incompatibilities.append(ConflictItem(
                    conflicted_product_id=downstream_id,
                    conflicted_product_name=d_prod.name if d_prod else str(downstream_id),
                    conflicted_product_vendor=d_prod.vendor if d_prod else "Unknown",
                    reason=f"Product requires incompatible component '{products_by_id[c_id].name if c_id in products_by_id else str(c_id)}'",
                    conflict_path=[root_product.name, "conflicts with", str(c_id), "required by", d_prod.name if d_prod else str(downstream_id)],
                    evidence=ev,
                ))

    # 3. Direct Integrations
    direct_integrations: list[ImpactItem] = []
    seen_integrations: set[uuid.UUID] = set()
    for i_id, ev in integrates_adj.get(product_id, []):
        if i_id not in seen_integrations and i_id != product_id:
            seen_integrations.add(i_id)
            i_prod = products_by_id.get(i_id)
            direct_integrations.append(ImpactItem(
                product_id=i_id,
                name=i_prod.name if i_prod else str(i_id),
                vendor=i_prod.vendor if i_prod else "Unknown",
                ownership=i_prod.ownership if i_prod else "own",
                depth=1,
                path=[root_product.name, i_prod.name if i_prod else str(i_id)],
                evidence=ev,
            ))

    # 4. Alternatives
    alternatives: list[ImpactItem] = []
    seen_alts: set[uuid.UUID] = set()
    for a_id, ev in alternative_adj.get(product_id, []):
        if a_id not in seen_alts and a_id != product_id:
            seen_alts.add(a_id)
            a_prod = products_by_id.get(a_id)
            alternatives.append(ImpactItem(
                product_id=a_id,
                name=a_prod.name if a_prod else str(a_id),
                vendor=a_prod.vendor if a_prod else "Unknown",
                ownership=a_prod.ownership if a_prod else "own",
                depth=1,
                path=[root_product.name, a_prod.name if a_prod else str(a_id)],
                evidence=ev,
            ))

    # 5. Reference Architectures
    relevant_archs: list[ReferenceArchitectureOut] = []
    if reference_architectures:
        for arch in reference_architectures:
            arch_pids = [rp.product_id for rp in arch.products]
            if product_id in arch_pids:
                prod_items: list[ReferenceArchitectureProductOut] = []
                for rp in arch.products:
                    p = products_by_id.get(rp.product_id)
                    prod_items.append(ReferenceArchitectureProductOut(
                        product_id=rp.product_id,
                        product_name=p.name if p else "Unknown",
                        vendor=p.vendor if p else "Unknown",
                        ownership=p.ownership if p else "own",
                        category=p.category if p else "General",
                        role=rp.role,
                        notes=rp.notes,
                    ))
                relevant_archs.append(ReferenceArchitectureOut(
                    id=arch.id,
                    org_id=arch.org_id,
                    workspace_id=arch.workspace_id,
                    name=arch.name,
                    slug=arch.slug,
                    description=arch.description,
                    architecture_overview=arch.architecture_overview,
                    target_segment=arch.target_segment,
                    created_at=arch.created_at,
                    products=prod_items,
                ))

    return GraphQueryOut(
        product_id=product_id,
        product_name=root_product.name,
        vendor=root_product.vendor,
        ownership=root_product.ownership,
        all_prerequisites=all_prerequisites,
        all_incompatibilities=incompatibilities,
        direct_integrations=direct_integrations,
        alternatives=alternatives,
        reference_architectures=relevant_archs,
    )


def get_neighborhood(
    product_id: uuid.UUID,
    edges: list[ProductEdge],
    products_by_id: dict[uuid.UUID, Product],
    reference_architectures: list[ReferenceArchitecture] | None = None,
) -> NeighborhoodOut:
    """Builds a neighborhood subgraph around a single product."""
    if product_id not in products_by_id:
        raise ValueError(f"Product {product_id} not found")

    center = products_by_id[product_id]
    center_out = ProductOut.model_validate(center)

    upstream_requires: list[ProductEdgeOut] = []
    downstream_required_by: list[ProductEdgeOut] = []
    conflicts: list[ProductEdgeOut] = []
    integrations: list[ProductEdgeOut] = []
    alternatives: list[ProductEdgeOut] = []
    bundles: list[ProductEdgeOut] = []
    replaces: list[ProductEdgeOut] = []
    migrates_to: list[ProductEdgeOut] = []

    for e in edges:
        if e.status != EdgeStatus.APPROVED:
            continue

        src_name = products_by_id[e.source_product_id].name if e.source_product_id in products_by_id else "Unknown"
        tgt_name = products_by_id[e.target_product_id].name if e.target_product_id in products_by_id else "Unknown"

        edge_out = ProductEdgeOut(
            id=e.id,
            org_id=e.org_id,
            workspace_id=e.workspace_id,
            source_product_id=e.source_product_id,
            source_product_name=src_name,
            target_product_id=e.target_product_id,
            target_product_name=tgt_name,
            relation_type=e.relation_type,
            evidence=e.evidence,
            confidence=e.confidence,
            document_id=e.document_id,
            is_ai_suggested=e.is_ai_suggested,
            status=e.status,
            rejection_reason=e.rejection_reason,
            created_at=e.created_at,
        )

        if e.source_product_id == product_id:
            if e.relation_type == RelationType.REQUIRES:
                upstream_requires.append(edge_out)
            elif e.relation_type == RelationType.CONFLICTS_WITH:
                conflicts.append(edge_out)
            elif e.relation_type == RelationType.INTEGRATES_WITH:
                integrations.append(edge_out)
            elif e.relation_type == RelationType.ALTERNATIVE_TO:
                alternatives.append(edge_out)
            elif e.relation_type == RelationType.BUNDLES_WITH:
                bundles.append(edge_out)
            elif e.relation_type == RelationType.REPLACES:
                replaces.append(edge_out)
            elif e.relation_type == RelationType.MIGRATES_TO:
                migrates_to.append(edge_out)
        elif e.target_product_id == product_id:
            if e.relation_type == RelationType.REQUIRES:
                downstream_required_by.append(edge_out)
            elif e.relation_type == RelationType.CONFLICTS_WITH:
                conflicts.append(edge_out)
            elif e.relation_type == RelationType.INTEGRATES_WITH:
                integrations.append(edge_out)
            elif e.relation_type == RelationType.ALTERNATIVE_TO:
                alternatives.append(edge_out)
            elif e.relation_type == RelationType.BUNDLES_WITH:
                bundles.append(edge_out)

    relevant_archs: list[ReferenceArchitectureOut] = []
    if reference_architectures:
        for arch in reference_architectures:
            arch_pids = [rp.product_id for rp in arch.products]
            if product_id in arch_pids:
                prod_items: list[ReferenceArchitectureProductOut] = []
                for rp in arch.products:
                    p = products_by_id.get(rp.product_id)
                    prod_items.append(ReferenceArchitectureProductOut(
                        product_id=rp.product_id,
                        product_name=p.name if p else "Unknown",
                        vendor=p.vendor if p else "Unknown",
                        ownership=p.ownership if p else "own",
                        category=p.category if p else "General",
                        role=rp.role,
                        notes=rp.notes,
                    ))
                relevant_archs.append(ReferenceArchitectureOut(
                    id=arch.id,
                    org_id=arch.org_id,
                    workspace_id=arch.workspace_id,
                    name=arch.name,
                    slug=arch.slug,
                    description=arch.description,
                    architecture_overview=arch.architecture_overview,
                    target_segment=arch.target_segment,
                    created_at=arch.created_at,
                    products=prod_items,
                ))

    return NeighborhoodOut(
        center_product=center_out,
        upstream_requires=upstream_requires,
        downstream_required_by=downstream_required_by,
        conflicts=conflicts,
        integrations=integrations,
        alternatives=alternatives,
        bundles=bundles,
        replaces=replaces,
        migrates_to=migrates_to,
        reference_architectures=relevant_archs,
    )


def build_portfolio_graph(
    products: list[Product],
    edges: list[ProductEdge],
) -> PortfolioGraphOut:
    """Assembles node-link data for the visual graph."""
    nodes: list[GraphNode] = []
    categories: set[str] = set()
    vendors: set[str] = set()

    for p in products:
        categories.add(p.category)
        vendors.add(p.vendor)
        doc_count = len(p.collateral_document_ids or [])
        cap_count = len(p.capabilities or [])

        nodes.append(GraphNode(
            id=str(p.id),
            name=p.name,
            slug=p.slug,
            vendor=p.vendor,
            ownership=p.ownership,
            category=p.category,
            tier=p.tier,
            deployment_model=p.deployment_model,
            lifecycle_status=p.lifecycle_status,
            capability_count=cap_count,
            collateral_count=doc_count,
        ))

    links: list[GraphLink] = []
    relation_types: set[str] = set()

    for e in edges:
        relation_types.add(e.relation_type)
        links.append(GraphLink(
            id=str(e.id),
            source=str(e.source_product_id),
            target=str(e.target_product_id),
            relation_type=e.relation_type,
            evidence=e.evidence,
            confidence=e.confidence,
            status=e.status,
            is_ai_suggested=e.is_ai_suggested,
        ))

    return PortfolioGraphOut(
        nodes=nodes,
        edges=links,
        categories=sorted(categories),
        vendors=sorted(vendors),
        relation_types=sorted(relation_types),
    )
