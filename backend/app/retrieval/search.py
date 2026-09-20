"""Hybrid retrieval: pgvector + PostgreSQL full-text search, fused with RRF.

Shape of a query:

    candidates CTE   = chunks joined to documents, filtered by permissions + corpus
                       rules + caller filters
    vector branch    = candidates ordered by cosine distance, limited to CANDIDATE_K
    keyword branch   = candidates matching websearch_to_tsquery, ranked by ts_rank_cd
    fusion           = RRF over the two rank lists, in Python, deterministic
    hydration        = fetch the top-K rows with their citation anchors

Both branches read from the **same** candidate CTE. That is what makes "filters apply
before fusion" a structural property rather than a promise: there is no path from an
unfiltered chunk into either rank list.

`mode` exists so the plan's required baseline comparison (vector-only vs keyword-only
vs hybrid) is one parameter, not three code paths that can drift apart.
"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from typing import Literal

from sqlalchemy import Float, cast, func, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.logging import get_logger
from app.db.models import Document, DocumentChunk
from app.embeddings.factory import get_embedding_provider
from app.retrieval.fusion import RankedList, reciprocal_rank_fusion
from app.retrieval.permissions import assert_enforced, build_predicate_set
from app.retrieval.spec import Origin, PredicateSet, RetrievalFilters
from app.retrieval.sql import compile_predicate_set
from app.security.principal import Principal

logger = get_logger(__name__)

SearchMode = Literal["hybrid", "vector", "keyword"]


@dataclass
class SearchHit:
    chunk_id: str
    document_id: str
    document_title: str | None
    original_filename: str
    file_type: str
    chunk_index: int
    text: str
    citation: str
    page_number: int | None = None
    slide_number: int | None = None
    sheet_name: str | None = None
    cell_range: str | None = None
    section_title: str | None = None
    heading_path: list[str] = field(default_factory=list)
    vendor: str | None = None
    ownership: str | None = None
    approval_state: str | None = None
    sensitivity: str | None = None
    valid_until: str | None = None
    is_stale: bool = False
    injection_flagged: bool = False
    rrf_score: float = 0.0
    ranks: dict[str, int] = field(default_factory=dict)
    branch_scores: dict[str, float] = field(default_factory=dict)


@dataclass
class SearchResponse:
    query: str
    mode: str
    hits: list[SearchHit]
    top_k: int
    candidate_k: int
    rrf_k: int
    candidate_count: int
    predicates: list[dict]
    branches: dict[str, list[dict]]
    timings_ms: dict[str, float]
    principal: dict


def search(
    db: Session,
    *,
    principal: Principal,
    query: str,
    filters: RetrievalFilters | None = None,
    mode: SearchMode = "hybrid",
    top_k: int | None = None,
    candidate_k: int | None = None,
    rrf_k: int | None = None,
    include_text: bool = True,
) -> SearchResponse:
    query = (query or "").strip()
    if not query:
        raise ValueError("query must not be empty")

    top_k = top_k or settings.top_k
    candidate_k = candidate_k or settings.candidate_k
    rrf_k = rrf_k or settings.rrf_k
    timings: dict[str, float] = {}
    started = time.perf_counter()

    predicate_set: PredicateSet = build_predicate_set(principal, filters)
    # Belt and braces: `build_predicate_set` already asserts, and so does this, so
    # that a future caller assembling its own set cannot skip the check.
    assert_enforced(predicate_set)
    where_clause = compile_predicate_set(predicate_set)

    candidates = (
        select(DocumentChunk.id.label("chunk_id"))
        .join(Document, Document.id == DocumentChunk.document_id)
        .where(where_clause)
        .cte("candidates")
    )

    mark = time.perf_counter()
    candidate_count = db.scalar(select(func.count()).select_from(candidates)) or 0
    timings["candidates_ms"] = _ms(mark)

    branches: list[RankedList] = []

    if mode in ("hybrid", "vector"):
        mark = time.perf_counter()
        vector = get_embedding_provider().embed_query(query)
        timings["embed_ms"] = _ms(mark)

        mark = time.perf_counter()
        distance = DocumentChunk.embedding.cosine_distance(vector).label("distance")
        rows = db.execute(
            select(DocumentChunk.id, distance)
            .join(candidates, candidates.c.chunk_id == DocumentChunk.id)
            .where(DocumentChunk.embedding.isnot(None))
            .order_by(distance)
            .limit(candidate_k)
        ).all()
        timings["vector_ms"] = _ms(mark)
        branches.append(
            RankedList(
                name="vector",
                ids=[str(row[0]) for row in rows],
                # Reported as similarity so a bigger number is always better,
                # matching the keyword branch. Avoids a class of reading errors.
                scores={str(row[0]): 1.0 - float(row[1]) for row in rows},
            )
        )

    if mode in ("hybrid", "keyword"):
        mark = time.perf_counter()
        tsquery = func.websearch_to_tsquery(settings.fts_config, query)
        rank = cast(func.ts_rank_cd(DocumentChunk.search_vector, tsquery), Float).label("rank")
        rows = db.execute(
            select(DocumentChunk.id, rank)
            .join(candidates, candidates.c.chunk_id == DocumentChunk.id)
            .where(DocumentChunk.search_vector.op("@@")(tsquery))
            .order_by(rank.desc())
            .limit(candidate_k)
        ).all()
        timings["keyword_ms"] = _ms(mark)
        branches.append(
            RankedList(
                name="keyword",
                ids=[str(row[0]) for row in rows],
                scores={str(row[0]): float(row[1]) for row in rows},
            )
        )

    mark = time.perf_counter()
    fused = reciprocal_rank_fusion(branches, k=rrf_k, limit=top_k)
    timings["fuse_ms"] = _ms(mark)

    mark = time.perf_counter()
    hits = _hydrate(db, fused, include_text=include_text) if fused else []
    timings["hydrate_ms"] = _ms(mark)
    timings["total_ms"] = _ms(started)

    logger.info(
        "search mode=%s q=%r candidates=%s hits=%s total=%.1fms",
        mode,
        query[:80],
        candidate_count,
        len(hits),
        timings["total_ms"],
    )

    return SearchResponse(
        query=query,
        mode=mode,
        hits=hits,
        top_k=top_k,
        candidate_k=candidate_k,
        rrf_k=rrf_k,
        candidate_count=candidate_count,
        predicates=predicate_set.describe(),
        branches={
            branch.name: [
                {"rank": rank, "chunk_id": chunk_id, "score": branch.scores.get(chunk_id)}
                for chunk_id, rank in sorted(branch.ranks().items(), key=lambda kv: kv[1])
            ]
            for branch in branches
        },
        timings_ms={key: round(value, 2) for key, value in timings.items()},
        principal=principal.describe(),
    )


def _hydrate(db: Session, fused, *, include_text: bool) -> list[SearchHit]:
    from datetime import date

    by_id = {hit.id: hit for hit in fused}
    uuid_ids = [uuid.UUID(k) if isinstance(k, str) else k for k in by_id]
    rows = db.execute(
        select(DocumentChunk, Document)
        .join(Document, Document.id == DocumentChunk.document_id)
        .where(DocumentChunk.id.in_(uuid_ids))
    ).all()

    today = date.today()
    hits: list[SearchHit] = []
    for chunk, document in rows:
        fusion_hit = by_id[str(chunk.id)]
        anchor_label = (chunk.chunk_metadata or {}).get("citation") or ""
        hits.append(
            SearchHit(
                chunk_id=str(chunk.id),
                document_id=str(document.id),
                document_title=document.title,
                original_filename=document.original_filename,
                file_type=document.file_type,
                chunk_index=chunk.chunk_index,
                text=chunk.text if include_text else "",
                citation=f"{document.title or document.original_filename}"
                + (f", {anchor_label}" if anchor_label else ""),
                page_number=chunk.page_number,
                slide_number=chunk.slide_number,
                sheet_name=chunk.sheet_name,
                cell_range=chunk.cell_range,
                section_title=chunk.section_title,
                heading_path=list(chunk.heading_path or []),
                vendor=document.vendor,
                ownership=document.ownership,
                approval_state=document.approval_state,
                sensitivity=document.sensitivity,
                valid_until=document.valid_until.isoformat() if document.valid_until else None,
                is_stale=bool(document.valid_until and document.valid_until < today),
                injection_flagged=bool(chunk.injection_flags),
                rrf_score=fusion_hit.score,
                ranks=fusion_hit.ranks,
                branch_scores=fusion_hit.raw_scores,
            )
        )

    # Preserve fusion order; the IN () above returns rows in physical order.
    order = {hit.id: position for position, hit in enumerate(fused)}
    hits.sort(key=lambda hit: order[hit.chunk_id])
    return hits


def _ms(since: float) -> float:
    return (time.perf_counter() - since) * 1000.0


def permission_predicate_count(principal: Principal) -> int:
    """Used by the regression test that guards the Phase 2 exit criterion."""
    return len(build_predicate_set(principal).by_origin(Origin.PERMISSION))
