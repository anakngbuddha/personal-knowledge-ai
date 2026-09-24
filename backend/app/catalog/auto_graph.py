"""Propose solution-selling relationships from the product list.

One model call reads confirmed products and files edges and use-case links
as suggestions. Existing pairs, including rejected ones, are left alone.
"""

from __future__ import annotations

import json
import re
import uuid
from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.catalog.models import slugify
from app.core.config import settings
from app.core.logging import get_logger
from app.db.models import (
    ContextKind,
    CurationStatus,
    EdgeStatus,
    Product,
    ProductCapability,
    ProductContextLink,
    ProductEdge,
    RelationType,
    SellingContext,
)
from app.llm.base import LLMProvider
from app.llm.factory import get_llm_provider

logger = get_logger(__name__)

MAX_PROPOSALS = 40

PRODUCT_RELATIONS = frozenset(
    {
        RelationType.BUNDLES_WITH,
        RelationType.RECOMMENDED_WITH,
        RelationType.CROSS_SELL,
        RelationType.REQUIRES,
        RelationType.INTEGRATES_WITH,
        RelationType.ALTERNATIVE_TO,
    }
)

_PROMPT = """You help a salesperson bundle the products they already sell.
Given the product list, propose relationships that make a solution easier to sell.
Use only these product-to-product types: bundles_with, recommended_with, cross_sell, requires, integrates_with, alternative_to.
Use only these context types: suits_use_case, certified_for, requires_license.
Context kinds: use_case, room_type, platform.
Every item needs a one-sentence rationale that names the product fields you used.
Return JSON only, no markdown:
{"edges":[{"source":"","target":"","relation_type":"","evidence":"","confidence":0.8}],"contexts":[{"product":"","kind":"use_case","name":"","relation_type":"suits_use_case","evidence":"","confidence":0.8}]}
"""


@dataclass
class AutoGraphResult:
    edges: list[ProductEdge] = field(default_factory=list)
    context_links: list[ProductContextLink] = field(default_factory=list)

    @property
    def proposed(self) -> int:
        return len(self.edges) + len(self.context_links)


def suggest_solution_graph(
    db: Session,
    *,
    workspace_id: uuid.UUID,
    org_id: uuid.UUID,
    provider: LLMProvider | None = None,
) -> AutoGraphResult:
    """File selling relationships for the confirmed products in one workspace."""
    products = list(
        db.scalars(
            select(Product)
            .options(selectinload(Product.capabilities).selectinload(ProductCapability.capability))
            .where(
                Product.workspace_id == workspace_id,
                Product.curation_status == CurationStatus.CONFIRMED,
            )
        ).all()
    )
    if len(products) < 2:
        return AutoGraphResult()

    llm = provider or get_llm_provider()
    answer = llm.generate_grounded_answer(
        _catalog_brief(products),
        [],
        system_prompt=_PROMPT,
    )
    payload = _parse_payload(answer.text or "")
    if payload is None:
        logger.info("auto-graph returned no usable JSON for workspace %s", workspace_id)
        return AutoGraphResult()

    by_name = {p.name.strip().lower(): p for p in products}
    existing_edges = {
        (e.source_product_id, e.target_product_id, e.relation_type)
        for e in db.scalars(select(ProductEdge).where(ProductEdge.workspace_id == workspace_id)).all()
    }
    existing_links = {
        (link.product_id, link.context_id, link.relation_type)
        for link in db.scalars(
            select(ProductContextLink).where(ProductContextLink.workspace_id == workspace_id)
        ).all()
    }

    result = AutoGraphResult()
    for raw in payload.get("edges") or []:
        if result.proposed >= MAX_PROPOSALS:
            break
        edge = _edge_from_raw(raw, by_name, existing_edges, org_id, workspace_id)
        if edge is None:
            continue
        db.add(edge)
        existing_edges.add((edge.source_product_id, edge.target_product_id, edge.relation_type))
        result.edges.append(edge)

    for raw in payload.get("contexts") or []:
        if result.proposed >= MAX_PROPOSALS:
            break
        link = _context_from_raw(db, raw, by_name, existing_links, org_id, workspace_id)
        if link is None:
            continue
        db.add(link)
        existing_links.add((link.product_id, link.context_id, link.relation_type))
        result.context_links.append(link)

    if result.proposed:
        db.commit()
        for row in (*result.edges, *result.context_links):
            db.refresh(row)
    return result


def _catalog_brief(products: list[Product]) -> str:
    lines: list[str] = []
    for product in products:
        caps = ", ".join(
            pc.capability.name for pc in product.capabilities if pc.capability is not None
        )
        lines.append(
            f"- {product.name} | vendor={product.vendor} | category={product.category} | "
            f"lifecycle={product.lifecycle_status} | {product.description or 'no description'} | "
            f"capabilities={caps or 'none'}"
        )
    return "Products:\n" + "\n".join(lines)


def _parse_payload(text: str) -> dict | None:
    cleaned = text.strip()
    fence = re.search(r"\{.*\}", cleaned, re.DOTALL)
    if fence:
        cleaned = fence.group(0)
    try:
        data = json.loads(cleaned)
    except json.JSONDecodeError:
        return None
    return data if isinstance(data, dict) else None


def _confidence(raw: object) -> float:
    try:
        value = float(raw)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return 0.0
    return max(0.0, min(1.0, value))


def _status_for(confidence: float) -> str:
    if confidence >= settings.graph_auto_accept_confidence:
        return EdgeStatus.APPROVED
    return EdgeStatus.PENDING_REVIEW


def _evidence(raw: object) -> str:
    text = str(raw or "").strip()
    if len(text) < 8:
        return ""
    return text[:2000]


def _edge_from_raw(
    raw: object,
    by_name: dict[str, Product],
    existing: set[tuple],
    org_id: uuid.UUID,
    workspace_id: uuid.UUID,
) -> ProductEdge | None:
    if not isinstance(raw, dict):
        return None
    relation = str(raw.get("relation_type") or "").strip().lower()
    if relation not in PRODUCT_RELATIONS:
        return None
    evidence = _evidence(raw.get("evidence"))
    if not evidence:
        return None
    source = by_name.get(str(raw.get("source") or "").strip().lower())
    target = by_name.get(str(raw.get("target") or "").strip().lower())
    if source is None or target is None or source.id == target.id:
        return None
    signature = (source.id, target.id, relation)
    if signature in existing:
        return None
    confidence = _confidence(raw.get("confidence"))
    return ProductEdge(
        org_id=org_id,
        workspace_id=workspace_id,
        source_product_id=source.id,
        target_product_id=target.id,
        relation_type=relation,
        evidence=evidence,
        confidence=confidence,
        is_ai_suggested=True,
        status=_status_for(confidence),
    )


def _context_from_raw(
    db: Session,
    raw: object,
    by_name: dict[str, Product],
    existing: set[tuple],
    org_id: uuid.UUID,
    workspace_id: uuid.UUID,
) -> ProductContextLink | None:
    if not isinstance(raw, dict):
        return None
    relation = str(raw.get("relation_type") or RelationType.SUITS_USE_CASE).strip().lower()
    if relation not in ProductContextLink.CONTEXT_RELATIONS:
        return None
    kind = str(raw.get("kind") or "").strip().lower()
    if kind not in ContextKind.ALL:
        return None
    name = str(raw.get("name") or "").strip()
    evidence = _evidence(raw.get("evidence"))
    product = by_name.get(str(raw.get("product") or "").strip().lower())
    if product is None or not name or not evidence:
        return None
    context = _get_or_create_context(db, org_id, workspace_id, kind, name)
    signature = (product.id, context.id, relation)
    if signature in existing:
        return None
    confidence = _confidence(raw.get("confidence"))
    return ProductContextLink(
        org_id=org_id,
        workspace_id=workspace_id,
        product_id=product.id,
        context_id=context.id,
        relation_type=relation,
        evidence=evidence,
        confidence=confidence,
        is_ai_suggested=True,
        status=_status_for(confidence),
    )


def _get_or_create_context(
    db: Session,
    org_id: uuid.UUID,
    workspace_id: uuid.UUID,
    kind: str,
    name: str,
) -> SellingContext:
    slug = slugify(name)[:128] or "context"
    found = db.scalars(
        select(SellingContext).where(
            SellingContext.workspace_id == workspace_id,
            SellingContext.kind == kind,
            SellingContext.slug == slug,
        )
    ).first()
    if found is not None:
        return found
    created = SellingContext(
        org_id=org_id,
        workspace_id=workspace_id,
        kind=kind,
        name=name[:255],
        slug=slug,
        curation_status=CurationStatus.SUGGESTED,
        is_ai_suggested=True,
    )
    db.add(created)
    db.flush()
    return created
