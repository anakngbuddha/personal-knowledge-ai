from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.errors import PermissionFilterMissing
from app.db.session import get_db
from app.retrieval.schemas import SearchIn, SearchOut
from app.retrieval.search import search as run_search
from app.retrieval.spec import RetrievalFilters
from app.retrieval.sql import UnknownFilterField
from app.security.deps import resolve_principal
from app.security.principal import Principal

router = APIRouter(tags=["retrieval"])

VALID_MODES = {"hybrid", "vector", "keyword"}


@router.post("/search", response_model=SearchOut)
def search_endpoint(
    payload: SearchIn,
    db: Session = Depends(get_db),
    principal: Principal = Depends(resolve_principal),
) -> SearchOut:
    """Hybrid retrieval with its scores and fusion inputs exposed.

    This is the Phase 2 deliverable and its own debug endpoint. `mode` selects
    vector-only, keyword-only, or hybrid so the plan's required baseline comparison
    runs against the same filters, the same permissions, and the same code path.
    """
    if payload.mode not in VALID_MODES:
        raise HTTPException(
            status_code=400,
            detail=f"mode must be one of: {', '.join(sorted(VALID_MODES))}",
        )

    filters = RetrievalFilters(**payload.filters.model_dump())
    try:
        result = run_search(
            db,
            principal=principal,
            query=payload.query,
            filters=filters,
            mode=payload.mode,  # type: ignore[arg-type]
            top_k=payload.top_k,
            candidate_k=payload.candidate_k,
            rrf_k=payload.rrf_k,
            include_text=payload.include_text,
        )
    except PermissionFilterMissing:
        # Never degrade to an unfiltered search. Loud failure is the requirement.
        raise HTTPException(
            status_code=500, detail="retrieval is misconfigured and was refused"
        ) from None
    except UnknownFilterField as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return SearchOut(
        query=result.query,
        mode=result.mode,
        top_k=result.top_k,
        candidate_k=result.candidate_k,
        rrf_k=result.rrf_k,
        candidate_count=result.candidate_count,
        hits=[hit.__dict__ for hit in result.hits],  # type: ignore[list-item]
        predicates=result.predicates,
        branches=result.branches,
        timings_ms=result.timings_ms,
        principal=result.principal,
    )
