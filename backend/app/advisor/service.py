"""4.2 The database half of the advisor.

:mod:`app.advisor.recommend` is deliberately pure. This module is the only place that
knows where the rows come from:

* the product list, minus suggestions, samples and end-of-life entries;
* the map, approved relationships only;
* one passage per shortlisted product, fetched with the same permission-aware search
  the rest of the app uses, so a recommendation can never cite a document the caller is
  not allowed to read.

Evidence is fetched in two passes on purpose. The first pass scores every product on
text alone, which costs nothing. Only the shortlist gets a search, so a 2,000-product
catalogue does not turn one question into 2,000 queries.
"""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.advisor.brief import CustomerBrief
from app.advisor.recommend import (
    Citation,
    Recommendation,
    recommend_from_rows,
)
from app.core.logging import get_logger
from app.db.models import (
    EdgeStatus,
    Product,
    ProductCapability,
    ProductContextLink,
    ProductEdge,
    SellingContext,
)
from app.retrieval.search import search as run_search
from app.retrieval.spec import RetrievalFilters
from app.security.principal import Principal

logger = get_logger(__name__)

#: How many products are worth a search each. Beyond this the answer is a catalogue.
EVIDENCE_SHORTLIST = 10

#: Products loaded per workspace. The importer caps a list at 2,000; this matches.
_PRODUCT_LIMIT = 2000


def build_recommendation(
    db: Session,
    *,
    principal: Principal,
    workspace_id: uuid.UUID,
    brief: CustomerBrief,
) -> Recommendation:
    """Read the rows, score once without evidence, then cite the shortlist."""
    products = list(
        db.scalars(
            select(Product)
            .options(selectinload(Product.capabilities).selectinload(ProductCapability.capability))
            .where(Product.workspace_id == workspace_id)
            .order_by(Product.name.asc())
            .limit(_PRODUCT_LIMIT)
        ).all()
    )
    if not products:
        return recommend_from_rows(brief=brief, products=[])

    edges = list(
        db.scalars(
            select(ProductEdge).where(
                ProductEdge.workspace_id == workspace_id,
                ProductEdge.status == EdgeStatus.APPROVED,
            )
        ).all()
    )
    context_links = list(
        db.scalars(
            select(ProductContextLink).where(
                ProductContextLink.workspace_id == workspace_id,
                ProductContextLink.status == EdgeStatus.APPROVED,
            )
        ).all()
    )
    contexts = list(
        db.scalars(
            select(SellingContext).where(SellingContext.workspace_id == workspace_id)
        ).all()
    )

    capabilities_by_product = {
        str(product.id): [
            link.capability.name for link in product.capabilities if link.capability is not None
        ]
        for product in products
    }
    rows = {
        "products": products,
        "edges": edges,
        "context_links": context_links,
        "contexts_by_id": {context.id: context for context in contexts},
        "capabilities_by_product": capabilities_by_product,
    }

    # Pass one: who is even in the running.
    draft = recommend_from_rows(brief=brief, **rows)
    shortlist = {pick.product_id: pick.name for pick in draft.picks}

    evidence = _gather_evidence(db, principal=principal, shortlist=shortlist, brief=brief)
    if not evidence:
        return draft

    # Pass two: the same scoring, now with the citations attached.
    return recommend_from_rows(brief=brief, evidence=evidence, **rows)


def _gather_evidence(
    db: Session,
    *,
    principal: Principal,
    shortlist: dict[str, str],
    brief: CustomerBrief,
) -> dict[str, list[Citation]]:
    """One search per shortlisted product. A failure costs a citation, never the answer."""
    evidence: dict[str, list[Citation]] = {}
    filters = RetrievalFilters(approved_only=True, exclude_injection_flagged=True)
    hint = " ".join(brief.platforms[:2]) or (brief.industry or "")

    for product_id, name in list(shortlist.items())[:EVIDENCE_SHORTLIST]:
        try:
            result = run_search(
                db,
                principal=principal,
                query=f"{name} {hint}".strip(),
                filters=filters,
                mode="hybrid",
                top_k=2,
            )
        except Exception:  # noqa: BLE001 - a missing citation is not a failed answer
            logger.debug("advisor: evidence search failed for %s", name, exc_info=True)
            continue
        citations = [
            Citation(
                label=hit.citation,
                document_title=hit.document_title,
                quote=(hit.text or "").strip(),
                page_number=hit.page_number,
            )
            for hit in result.hits
            if _mentions(hit, name)
        ]
        if citations:
            evidence[product_id] = citations[:2]
    return evidence


def _mentions(hit, name: str) -> bool:
    """A passage only counts as evidence for a product if it names it.

    Hybrid search returns the closest passages, not necessarily passages about this
    product. Attaching the nearest one anyway is how a citation ends up under a claim
    it does not support, so the name has to actually appear.
    """
    needle = (name or "").strip().lower()
    if not needle:
        return False
    haystack = f"{hit.text or ''} {hit.document_title or ''}".lower()
    if needle in haystack:
        return True
    # "Poly Studio X50" also matches a passage that only writes "Studio X50".
    words = [word for word in needle.split() if len(word) > 2]
    return len(words) > 1 and " ".join(words[1:]) in haystack
