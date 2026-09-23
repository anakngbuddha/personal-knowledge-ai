"""Retrieval filters, expressed as data.

Why an intermediate representation instead of building SQLAlchemy clauses directly:

* "Filters apply before fusion" is a claim that has to be *checkable*. With the
  predicate set as data, a test can assert that the permission predicates are present
  in the candidate set and that both ranking branches read from that same set. With
  clauses assembled inline you can only assert on a SQL string and hope.
* Every predicate carries its `origin`, so the debug endpoint can show a human which
  predicates came from their filters and which came from their grants. When a search
  returns nothing, that distinction is the whole answer.
* The IR is pure Python, so the authorization logic is unit-tested without a database.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from enum import StrEnum


class Origin(StrEnum):
    PERMISSION = "permission"  # from the caller's grants. Never removable.
    CORPUS = "corpus"  # structural: current version, successfully ingested.
    FILTER = "filter"  # from the caller's request.


class Op(StrEnum):
    EQ = "eq"
    IN = "in"
    IS_NULL = "is_null"
    NOT_NULL = "not_null"
    IS_TRUE = "is_true"
    IS_FALSE = "is_false"
    CONTAINS_ANY = "contains_any"  # JSONB array overlap
    GTE_OR_NULL = "gte_or_null"  # freshness: valid_until >= date OR unset
    IN_OR_NULL = "in_or_null"  # account scope: mine OR unscoped
    NOT_IN = "not_in"


@dataclass(frozen=True)
class Predicate:
    field: str
    op: Op
    value: object = None
    origin: Origin = Origin.FILTER
    reason: str = ""

    def describe(self) -> dict:
        value = sorted(self.value) if isinstance(self.value, (set, frozenset)) else self.value
        if isinstance(value, date):
            value = value.isoformat()
        return {
            "field": self.field,
            "op": str(self.op),
            "value": value,
            "origin": str(self.origin),
            "reason": self.reason,
        }


@dataclass
class PredicateSet:
    predicates: list[Predicate] = field(default_factory=list)

    def add(self, predicate: Predicate) -> None:
        self.predicates.append(predicate)

    def extend(self, predicates: list[Predicate]) -> None:
        self.predicates.extend(predicates)

    def by_origin(self, origin: Origin) -> list[Predicate]:
        return [p for p in self.predicates if p.origin == origin]

    @property
    def has_permission_predicates(self) -> bool:
        return any(p.origin == Origin.PERMISSION for p in self.predicates)

    def describe(self) -> list[dict]:
        return [p.describe() for p in self.predicates]

    def __len__(self) -> int:
        return len(self.predicates)

    def __iter__(self):
        return iter(self.predicates)


@dataclass
class RetrievalFilters:
    """Caller-supplied narrowing. Every field is optional; none of them can widen
    what the caller's grants already allow, because the predicates are ANDed."""

    products: list[str] = field(default_factory=list)
    vendor: str | None = None
    ownership: str | None = None
    account_ref: str | None = None
    approval_states: list[str] = field(default_factory=list)
    sensitivities: list[str] = field(default_factory=list)
    file_types: list[str] = field(default_factory=list)
    document_ids: list[str] = field(default_factory=list)
    exclude_document_ids: list[str] = field(default_factory=list)
    fresh_as_of: date | None = None  # drop collateral whose valid_until has passed
    approved_only: bool = False
    exclude_injection_flagged: bool = False
    # Client RFP files are searchable when a query names them, and omitted from
    # every unscoped search. An explicit document id list is that opt-in.
    exclude_source_types: list[str] = field(default_factory=list)

    def to_predicates(self) -> list[Predicate]:
        out: list[Predicate] = []
        if self.products:
            out.append(
                Predicate(
                    "products_referenced",
                    Op.CONTAINS_ANY,
                    list(self.products),
                    Origin.FILTER,
                    "products filter",
                )
            )
        if self.vendor:
            out.append(Predicate("vendor", Op.EQ, self.vendor, Origin.FILTER, "vendor filter"))
        if self.ownership:
            out.append(
                Predicate("ownership", Op.EQ, self.ownership, Origin.FILTER, "ownership filter")
            )
        if self.account_ref:
            out.append(
                Predicate("account_ref", Op.EQ, self.account_ref, Origin.FILTER, "account filter")
            )
        states = list(self.approval_states)
        if self.approved_only:
            states = ["approved"]
        if states:
            out.append(
                Predicate(
                    "approval_state", Op.IN, set(states), Origin.FILTER, "approval state filter"
                )
            )
        if self.sensitivities:
            out.append(
                Predicate(
                    "sensitivity",
                    Op.IN,
                    set(self.sensitivities),
                    Origin.FILTER,
                    "sensitivity filter",
                )
            )
        if self.file_types:
            out.append(
                Predicate(
                    "file_type", Op.IN, set(self.file_types), Origin.FILTER, "document type filter"
                )
            )
        if self.document_ids:
            out.append(
                Predicate(
                    "id", Op.IN, set(self.document_ids), Origin.FILTER, "document id filter"
                )
            )
        if self.fresh_as_of is not None:
            out.append(
                Predicate(
                    "valid_until",
                    Op.GTE_OR_NULL,
                    self.fresh_as_of,
                    Origin.FILTER,
                    "freshness filter",
                )
            )
        if self.exclude_injection_flagged:
            out.append(
                Predicate(
                    "injection_flag_count",
                    Op.EQ,
                    0,
                    Origin.FILTER,
                    "exclude documents with instruction-like passages",
                )
            )
        if self.exclude_document_ids:
            out.append(
                Predicate(
                    "id",
                    Op.NOT_IN,
                    set(self.exclude_document_ids),
                    Origin.FILTER,
                    "exclude document ids filter",
                )
            )
        if self.exclude_source_types and not self.document_ids:
            out.append(
                Predicate(
                    "source_type",
                    Op.NOT_IN,
                    set(self.exclude_source_types),
                    Origin.FILTER,
                    "exclude client RFP intake from general retrieval",
                )
            )
        return out


def corpus_predicates() -> list[Predicate]:
    """Structural predicates. A superseded version, a half-ingested document, or a
    sample source is never a retrieval candidate, regardless of who is asking."""
    return [
        Predicate("is_current", Op.IS_TRUE, True, Origin.CORPUS, "current version only"),
        Predicate("status", Op.EQ, "ready", Origin.CORPUS, "fully ingested documents only"),
        # 3.3: the sample catalog is there to fill the screens, not to answer a real
        # question. It is excluded here rather than in a caller's filter so no code
        # path can forget to exclude it.
        Predicate(
            "is_demo",
            Op.IS_FALSE,
            False,
            Origin.CORPUS,
            "sample material never answers a real question",
        ),
    ]
