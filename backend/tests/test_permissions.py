"""Permission-aware retrieval.

Project_Plan.md Phase 2 exit criterion: "permission filtering has a test that fails
loudly if removed". This module is that test.

The guarantee is structural, not statistical: `build_predicate_set` cannot return a set
without `Origin.PERMISSION` predicates, and `assert_enforced` raises if one ever
reaches the query builder. Delete `predicates_for` and these tests go red immediately.
"""

import uuid

import pytest

from app.core.errors import PermissionFilterMissing
from app.retrieval.permissions import assert_enforced, build_predicate_set, predicates_for
from app.retrieval.spec import Op, Origin, PredicateSet, RetrievalFilters
from app.security.labels import Sensitivity
from app.security.principal import Principal, owner_principal, restricted_principal

ORG = uuid.uuid4()
OTHER_ORG = uuid.uuid4()


def fields(predicates, origin=None):
    return {
        predicate.field
        for predicate in predicates
        if origin is None or predicate.origin == origin
    }


def value_for(predicates, field):
    return next(p.value for p in predicates if p.field == field)


# ---------------------------------------------------------------- the load-bearing test


def test_every_principal_gets_permission_predicates():
    """No principal, however privileged, produces an unfiltered query."""
    for principal in (
        owner_principal(ORG),
        restricted_principal(ORG),
        restricted_principal(ORG, role="viewer", include_unapproved=False),
        restricted_principal(ORG, account_refs=None),
        Principal(org_id=ORG, user_id=None),
    ):
        predicates = predicates_for(principal)
        assert predicates, principal
        assert all(p.origin == Origin.PERMISSION for p in predicates)
        assert "org_id" in fields(predicates)
        assert "sensitivity" in fields(predicates)


def test_removing_the_permission_predicates_fails_loudly():
    """The tripwire. An empty or filter-only predicate set must never run."""
    with pytest.raises(PermissionFilterMissing):
        assert_enforced(PredicateSet())

    filters_only = PredicateSet()
    filters_only.extend(RetrievalFilters(vendor="Northwind").to_predicates())
    with pytest.raises(PermissionFilterMissing):
        assert_enforced(filters_only)


def test_tenant_isolation_predicate_pins_the_callers_org():
    predicates = predicates_for(restricted_principal(ORG))
    assert value_for(predicates, "org_id") == ORG
    assert value_for(predicates, "org_id") != OTHER_ORG


# ------------------------------------------------------------------------ sensitivity


def test_sensitivity_ceiling_is_enforced():
    internal = predicates_for(restricted_principal(ORG, max_sensitivity=Sensitivity.INTERNAL))
    allowed = value_for(internal, "sensitivity")
    assert allowed == {"public", "internal"}
    assert "confidential" not in allowed
    assert "customer_data" not in allowed
    assert "vendor_restricted" not in allowed


def test_customer_data_grant_does_not_imply_vendor_restricted():
    """`vendor_restricted` is contractual, not hierarchical. A customer-data grant is
    about confidentiality; partner NDA terms are a separate decision."""
    predicates = predicates_for(
        restricted_principal(ORG, max_sensitivity=Sensitivity.CUSTOMER_DATA)
    )
    allowed = value_for(predicates, "sensitivity")
    assert "customer_data" in allowed
    assert "vendor_restricted" not in allowed


def test_vendor_restricted_requires_its_own_flag():
    predicates = predicates_for(
        restricted_principal(
            ORG, max_sensitivity=Sensitivity.CONFIDENTIAL, allow_vendor_restricted=True
        )
    )
    assert "vendor_restricted" in value_for(predicates, "sensitivity")


def test_owner_sees_everything_by_decision():
    """Project_Plan.md section 0 decides collateral has a single owner. That is a
    decision, so it is asserted here rather than left to look like a hole."""
    allowed = value_for(predicates_for(owner_principal(ORG)), "sensitivity")
    assert allowed == {
        "public",
        "internal",
        "confidential",
        "customer_data",
        "vendor_restricted",
    }


# --------------------------------------------------------------------- account scoping


def test_account_scope_requires_a_grant_but_keeps_unscoped_material_visible():
    predicates = predicates_for(restricted_principal(ORG, account_refs=frozenset({"acme"})))
    account = next(p for p in predicates if p.field == "account_ref")
    assert account.op is Op.IN_OR_NULL
    assert account.value == {"acme"}


def test_no_grants_means_no_account_scoped_material_at_all():
    predicates = predicates_for(restricted_principal(ORG, account_refs=frozenset()))
    account = next(p for p in predicates if p.field == "account_ref")
    assert account.value == set()


def test_owner_has_no_account_predicate_because_scope_is_unlimited():
    assert "account_ref" not in fields(predicates_for(owner_principal(ORG)))


def test_viewer_only_sees_approved_collateral():
    predicates = predicates_for(
        restricted_principal(ORG, role="viewer", include_unapproved=False)
    )
    approval = next(p for p in predicates if p.field == "approval_state")
    assert approval.value == "approved"


# ------------------------------------------------------- filters cannot widen a grant


def test_a_caller_filter_cannot_widen_their_sensitivity_grant():
    """Both predicates are ANDed, so asking for `customer_data` while capped at
    `internal` yields nothing rather than a leak."""
    principal = restricted_principal(ORG, max_sensitivity=Sensitivity.INTERNAL)
    predicate_set = build_predicate_set(
        principal, RetrievalFilters(sensitivities=["customer_data"])
    )
    permission = next(
        p
        for p in predicate_set
        if p.field == "sensitivity" and p.origin == Origin.PERMISSION
    )
    caller = next(
        p for p in predicate_set if p.field == "sensitivity" and p.origin == Origin.FILTER
    )
    assert "customer_data" not in permission.value
    assert caller.value == {"customer_data"}
    assert not (set(permission.value) & set(caller.value))


def test_a_caller_filter_cannot_widen_their_account_grant():
    principal = restricted_principal(ORG, account_refs=frozenset({"acme"}))
    predicate_set = build_predicate_set(principal, RetrievalFilters(account_ref="globex"))
    permission = next(
        p for p in predicate_set if p.field == "account_ref" and p.origin == Origin.PERMISSION
    )
    assert permission.value == {"acme"}


def test_corpus_predicates_are_always_present():
    predicate_set = build_predicate_set(owner_principal(ORG))
    corpus = fields(predicate_set, Origin.CORPUS)
    assert corpus == {"is_current", "status"}


def test_predicate_set_describes_where_each_predicate_came_from():
    described = build_predicate_set(
        restricted_principal(ORG), RetrievalFilters(vendor="Northwind")
    ).describe()
    origins = {entry["origin"] for entry in described}
    assert origins == {"permission", "corpus", "filter"}
    assert all(entry["reason"] for entry in described)
