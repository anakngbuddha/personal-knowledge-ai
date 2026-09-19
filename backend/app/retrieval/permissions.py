"""Permission-aware retrieval.

Project_Plan.md Phase 2: "candidates are filtered by the caller's grants at query
time, so a chunk the user may not read never reaches the model", and the phase exit
criterion is "permission filtering has a test that fails loudly if removed".

Two mechanisms make that true rather than aspirational:

1. `predicates_for` is the only place permission predicates are produced, and it
   always produces at least the tenant predicate. There is no code path that
   produces an empty permission set.
2. `assert_enforced` raises `PermissionFilterMissing` if a predicate set reaches the
   query builder without any `Origin.PERMISSION` entries. Deleting the call to
   `predicates_for` therefore turns every search into a 500, not a silent leak.
"""

from __future__ import annotations

from app.core.errors import PermissionFilterMissing
from app.retrieval.spec import Op, Origin, Predicate, PredicateSet
from app.security.labels import ApprovalState
from app.security.principal import Principal


def predicates_for(principal: Principal) -> list[Predicate]:
    predicates: list[Predicate] = [
        Predicate(
            "org_id",
            Op.EQ,
            principal.org_id,
            Origin.PERMISSION,
            "tenant isolation",
        ),
        Predicate(
            "sensitivity",
            Op.IN,
            set(principal.readable_sensitivities()),
            Origin.PERMISSION,
            f"sensitivity ceiling: {principal.max_sensitivity}"
            + ("" if principal.allow_vendor_restricted else ", no vendor-restricted material"),
        ),
    ]

    if not principal.sees_all_accounts:
        # Account-scoped material needs an explicit grant. Material with no account
        # (the product catalog, generic collateral) stays visible.
        predicates.append(
            Predicate(
                "account_ref",
                Op.IN_OR_NULL,
                set(principal.account_refs or ()),
                Origin.PERMISSION,
                "per-account grants",
            )
        )

    if not principal.include_unapproved:
        predicates.append(
            Predicate(
                "approval_state",
                Op.EQ,
                str(ApprovalState.APPROVED),
                Origin.PERMISSION,
                "role may only read approved collateral",
            )
        )

    return predicates


def build_predicate_set(principal: Principal, filters=None) -> PredicateSet:
    """Assemble the full candidate predicate set: permissions, corpus, then filters."""
    from app.retrieval.spec import corpus_predicates

    predicate_set = PredicateSet()
    predicate_set.extend(predicates_for(principal))
    predicate_set.extend(corpus_predicates())
    if filters is not None:
        predicate_set.extend(filters.to_predicates())
    assert_enforced(predicate_set)
    return predicate_set


def assert_enforced(predicate_set: PredicateSet) -> None:
    if not predicate_set.has_permission_predicates:
        raise PermissionFilterMissing(
            "retrieval attempted without permission predicates; refusing to run the query"
        )
