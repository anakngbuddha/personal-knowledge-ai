"""3.5 GraphRAG-lite: bring the map into the answer.

Search finds passages that look like the question. It does not know that the camera in
the question needs a licence, clashes with the switch the customer already owns, or has
a bigger sibling. That lives on the map, and until now no answer used it.

So before the prompt is built:

* find the products the question actually names, using the same normalised keys the map
  read uses, so "PanaCast 50" and "panacast-50" are one product;
* walk one or two hops out along the relationships worth walking (works with, needs,
  clashes with, is recommended with, pairs well with, is a step up to, is part of);
* hand the prompt a short list of plain-sentence facts, and let the caller pull in the
  neighbours' best passages so the model can cite them.

Two rules:

* only approved relationships are walked. A suggestion nobody has accepted is not a
  fact, and an answer must never quietly rely on one;
* the evidence attached to an edge is a quote from a document, so the block that carries
  it is fenced through ``wrap_untrusted`` before it reaches the model, exactly like any
  other passage.

The walking and matching are pure functions over rows, so both are tested without a
database.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.catalog.extraction import normalize_name
from app.core.config import settings
from app.core.logging import get_logger
from app.db.models import (
    EdgeStatus,
    Product,
    ProductContextLink,
    ProductEdge,
    RelationType,
    SellingContext,
    Workspace,
)

logger = get_logger(__name__)

#: A key shorter than this matches half the English language.
_MIN_KEY_LENGTH = 3

#: How much of an edge's quote is worth carrying into the prompt.
_EVIDENCE_CHARS = 240


@dataclass(frozen=True)
class GraphFact:
    subject: str
    reads_as: str
    object: str
    evidence: str = ""
    relation_type: str = ""

    @property
    def signature(self) -> tuple[str, str, str]:
        return (normalize_name(self.subject), self.relation_type, normalize_name(self.object))

    def as_line(self) -> str:
        line = f"- {self.subject} {self.reads_as} {self.object}."
        quote = (self.evidence or "").strip().replace("\n", " ")
        if quote:
            line += f' Because: "{quote[:_EVIDENCE_CHARS]}"'
        return line


@dataclass
class GraphContext:
    """What the map knows about the products this question names."""

    mentioned: list[str] = field(default_factory=list)
    neighbour_names: list[str] = field(default_factory=list)
    facts: list[GraphFact] = field(default_factory=list)

    @property
    def is_empty(self) -> bool:
        return not self.facts

    def as_lines(self) -> list[str]:
        return [fact.as_line() for fact in self.facts]

    def as_dict(self) -> dict:
        return {
            "mentioned": list(self.mentioned),
            "neighbours": list(self.neighbour_names),
            "facts": len(self.facts),
        }


# -- matching --------------------------------------------------------------


def product_keys(product) -> list[str]:
    keys = [normalize_name(getattr(product, "name", ""))]
    slug = getattr(product, "slug", "") or ""
    if slug:
        keys.append(normalize_name(slug.replace("-", " ")))
    for alias in getattr(product, "aliases", None) or []:
        keys.append(normalize_name(str(alias)))
    return [key for key in keys if len(key) >= _MIN_KEY_LENGTH]


def match_products(question: str, products) -> list:
    """Every product the question names, longest name first.

    Matching is on whole words inside the normalised question, so "Teams" does not match
    "Teamshare", and the longest name wins when two products share a prefix.
    """
    haystack = f" {normalize_name(question)} "
    scored: list[tuple[int, object]] = []
    for product in products:
        best = 0
        for key in product_keys(product):
            if f" {key} " in haystack and len(key) > best:
                best = len(key)
        if best:
            scored.append((best, product))
    scored.sort(key=lambda pair: pair[0], reverse=True)
    return [product for _, product in scored]


# -- walking ---------------------------------------------------------------


def expand_from_rows(
    *,
    seeds,
    products_by_id: dict,
    edges,
    context_links=(),
    contexts_by_id: dict | None = None,
    hops: int = 2,
    max_neighbours: int = 6,
) -> GraphContext:
    """Walk out from the named products. Pure: rows in, sentences out."""
    contexts_by_id = contexts_by_id or {}
    seed_ids = [getattr(seed, "id") for seed in seeds]
    result = GraphContext(mentioned=[getattr(seed, "name", "") for seed in seeds])

    seen_signatures: set[tuple[str, str, str]] = set()
    visited = set(seed_ids)
    frontier = set(seed_ids)

    def add(fact: GraphFact) -> None:
        if fact.signature in seen_signatures:
            return
        seen_signatures.add(fact.signature)
        result.facts.append(fact)

    for _ in range(max(1, hops)):
        if not frontier:
            break
        next_frontier: set = set()
        for edge in edges:
            relation = getattr(edge, "relation_type", "")
            if relation not in RelationType.EXPANDABLE:
                continue
            source_id = getattr(edge, "source_product_id", None)
            target_id = getattr(edge, "target_product_id", None)
            if source_id not in frontier and target_id not in frontier:
                continue
            source = products_by_id.get(source_id)
            target = products_by_id.get(target_id)
            if source is None or target is None:
                continue
            add(
                GraphFact(
                    subject=source.name,
                    reads_as=RelationType.words(relation),
                    object=target.name,
                    evidence=getattr(edge, "evidence", "") or "",
                    relation_type=relation,
                )
            )
            for far_id in (source_id, target_id):
                if far_id in visited or far_id not in products_by_id:
                    continue
                if len(result.neighbour_names) >= max_neighbours:
                    continue
                visited.add(far_id)
                next_frontier.add(far_id)
                result.neighbour_names.append(products_by_id[far_id].name)
        frontier = next_frontier

    # What the named products are sold against is worth saying out loud too.
    for link in context_links:
        if getattr(link, "product_id", None) not in seed_ids:
            continue
        product = products_by_id.get(getattr(link, "product_id", None))
        context = contexts_by_id.get(getattr(link, "context_id", None))
        if product is None or context is None:
            continue
        add(
            GraphFact(
                subject=product.name,
                reads_as=RelationType.words(getattr(link, "relation_type", "")),
                object=context.name,
                evidence=getattr(link, "evidence", "") or "",
                relation_type=getattr(link, "relation_type", ""),
            )
        )

    return result


# -- the database half -----------------------------------------------------


def expand(db: Session, *, workspace_id: uuid.UUID | None, question: str, org_id: uuid.UUID | None = None) -> GraphContext:
    """Look the question up on the map. Never raises: an empty result is an answer."""
    if not settings.graph_expansion_enabled or workspace_id is None or not (question or "").strip():
        return GraphContext()
    if org_id is None:
        return GraphContext()
    try:
        if db.scalar(select(Workspace.id).where(Workspace.id == workspace_id, Workspace.org_id == org_id)) is None:
            return GraphContext()
        products = list(
            db.scalars(select(Product).where(Product.workspace_id == workspace_id, Product.org_id == org_id).limit(2000)).all()
        )
        if not products:
            return GraphContext()
        seeds = match_products(question, products)
        if not seeds:
            return GraphContext()

        edges = list(
            db.scalars(
                select(ProductEdge).where(
                    ProductEdge.workspace_id == workspace_id, ProductEdge.org_id == org_id,
                    ProductEdge.status == EdgeStatus.APPROVED,
                )
                .limit(2000)
            ).all()
        )
        links = list(
            db.scalars(
                select(ProductContextLink).where(
                    ProductContextLink.workspace_id == workspace_id, ProductContextLink.org_id == org_id,
                    ProductContextLink.status == EdgeStatus.APPROVED,
                )
                .limit(2000)
            ).all()
        )
        contexts = list(
            db.scalars(
                select(SellingContext).where(SellingContext.workspace_id == workspace_id, SellingContext.org_id == org_id)
                .limit(2000)
            ).all()
        )
    except Exception:  # noqa: BLE001 - the map is never worth failing an answer over
        logger.debug("map lookup failed", exc_info=True)
        return GraphContext()

    context = expand_from_rows(
        seeds=seeds,
        products_by_id={product.id: product for product in products},
        edges=edges,
        context_links=links,
        contexts_by_id={item.id: item for item in contexts},
        hops=settings.graph_expansion_hops,
        max_neighbours=settings.graph_expansion_max_neighbours,
    )
    if not context.is_empty:
        logger.info("map lookup: %s", context.as_dict())
    return context
