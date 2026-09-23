"""Hybrid retrieval tool. Reuses permission-aware search and wraps hits as data."""

from __future__ import annotations

from typing import Any

from app.core.config import settings
from app.documents.injection import wrap_untrusted
from app.retrieval.search import search as run_search
from app.retrieval.spec import RetrievalFilters
from app.security.labels import SourceType
from app.tools.registry import ToolContext


def hybrid_search_tool(
    ctx: ToolContext,
    query: str,
    *,
    vendor: str | None = None,
    products: list[str] | None = None,
) -> dict[str, Any]:
    filters = RetrievalFilters(
        products=list(products or []),
        vendor=vendor,
        approved_only=True,
        exclude_injection_flagged=True,
        exclude_source_types=[SourceType.RFP_INTAKE],
    )
    result = run_search(
        ctx.db,
        principal=ctx.principal,
        query=query,
        filters=filters,
        mode="hybrid",
        top_k=min(8, settings.generation_max_context_chunks),
    )
    hits = []
    for hit in result.hits:
        fenced = wrap_untrusted(hit.text, source=hit.citation)
        hits.append(
            {
                "citation": hit.citation,
                "document_title": hit.document_title,
                "fenced_text": fenced,
                "vendor": hit.vendor,
                "approval_state": hit.approval_state,
                "page_number": hit.page_number,
            }
        )
    return {"query": query, "hit_count": len(hits), "hits": hits}
