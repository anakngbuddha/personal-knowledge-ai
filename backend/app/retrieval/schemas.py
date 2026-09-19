from datetime import date

from pydantic import BaseModel, ConfigDict, Field


class SearchFiltersIn(BaseModel):
    """Caller-supplied narrowing. Required, not optional, per Phase 2: every field
    here maps to an indexed column and is applied before fusion."""

    model_config = ConfigDict(extra="forbid")

    products: list[str] = Field(default_factory=list)
    vendor: str | None = None
    ownership: str | None = None
    account_ref: str | None = None
    approval_states: list[str] = Field(default_factory=list)
    sensitivities: list[str] = Field(default_factory=list)
    file_types: list[str] = Field(default_factory=list)
    document_ids: list[str] = Field(default_factory=list)
    fresh_as_of: date | None = None
    approved_only: bool = False
    exclude_injection_flagged: bool = False


class SearchIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    query: str = Field(min_length=1, max_length=2000)
    mode: str = "hybrid"  # hybrid | vector | keyword
    top_k: int | None = Field(default=None, ge=1, le=50)
    candidate_k: int | None = Field(default=None, ge=1, le=200)
    rrf_k: int | None = Field(default=None, ge=1, le=1000)
    filters: SearchFiltersIn = Field(default_factory=SearchFiltersIn)
    include_text: bool = True


class SearchHitOut(BaseModel):
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
    heading_path: list[str] = Field(default_factory=list)
    vendor: str | None = None
    ownership: str | None = None
    approval_state: str | None = None
    sensitivity: str | None = None
    valid_until: str | None = None
    is_stale: bool = False
    injection_flagged: bool = False
    rrf_score: float = 0.0
    ranks: dict[str, int] = Field(default_factory=dict)
    branch_scores: dict[str, float] = Field(default_factory=dict)


class SearchOut(BaseModel):
    """The debug endpoint's contract: scores and fusion inputs are always exposed.

    Kept in the normal response rather than behind a flag, because Phase 2's exit
    criterion is a *written baseline*, and a baseline you cannot see is not one.
    """

    query: str
    mode: str
    top_k: int
    candidate_k: int
    rrf_k: int
    candidate_count: int
    hits: list[SearchHitOut]
    predicates: list[dict]
    branches: dict[str, list[dict]]
    timings_ms: dict[str, float]
    principal: dict
