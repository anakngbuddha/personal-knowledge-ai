"""Filter specification: every Phase 2 filter dimension maps to a predicate, and the
empty-allow-list case matches nothing instead of everything."""

from datetime import date

import pytest

from app.retrieval.spec import Op, Origin, Predicate, PredicateSet, RetrievalFilters, corpus_predicates


def test_no_filters_produces_no_predicates():
    assert RetrievalFilters().to_predicates() == []


def test_every_required_filter_dimension_is_supported():
    """Phase 2 lists these as required, not optional: product, vendor, account,
    approval state, freshness, sensitivity, document type."""
    filters = RetrievalFilters(
        products=["OrbitCloud"],
        vendor="Northwind",
        ownership="resold",
        account_ref="acme",
        approval_states=["approved"],
        sensitivities=["internal"],
        file_types=["pdf", "pptx"],
        fresh_as_of=date(2026, 9, 19),
    )
    fields = {predicate.field for predicate in filters.to_predicates()}
    assert fields == {
        "products_referenced",
        "vendor",
        "ownership",
        "account_ref",
        "approval_state",
        "sensitivity",
        "file_type",
        "valid_until",
    }
    assert all(p.origin == Origin.FILTER for p in filters.to_predicates())


def test_approved_only_overrides_a_looser_approval_filter():
    filters = RetrievalFilters(approval_states=["draft", "approved"], approved_only=True)
    predicate = next(p for p in filters.to_predicates() if p.field == "approval_state")
    assert predicate.value == {"approved"}


def test_freshness_treats_missing_expiry_as_fresh():
    predicate = next(
        p
        for p in RetrievalFilters(fresh_as_of=date(2026, 1, 1)).to_predicates()
        if p.field == "valid_until"
    )
    assert predicate.op is Op.GTE_OR_NULL


def test_products_use_array_overlap():
    predicate = next(
        p
        for p in RetrievalFilters(products=["A", "B"]).to_predicates()
        if p.field == "products_referenced"
    )
    assert predicate.op is Op.CONTAINS_ANY
    assert predicate.value == ["A", "B"]


def test_corpus_predicates_exclude_superseded_and_unfinished_documents():
    fields = {p.field: p for p in corpus_predicates()}
    assert fields["is_current"].op is Op.IS_TRUE
    assert fields["status"].value == "ready"
    assert all(p.origin == Origin.CORPUS for p in corpus_predicates())


def test_predicate_set_partitions_by_origin():
    predicate_set = PredicateSet()
    predicate_set.add(Predicate("org_id", Op.EQ, 1, Origin.PERMISSION))
    predicate_set.extend(corpus_predicates())
    predicate_set.extend(RetrievalFilters(vendor="X").to_predicates())
    assert len(predicate_set) == 4
    assert len(predicate_set.by_origin(Origin.PERMISSION)) == 1
    assert len(predicate_set.by_origin(Origin.CORPUS)) == 2
    assert len(predicate_set.by_origin(Origin.FILTER)) == 1
    assert predicate_set.has_permission_predicates


def test_describe_is_json_safe():
    described = RetrievalFilters(
        fresh_as_of=date(2026, 9, 19), approval_states=["approved", "draft"]
    ).to_predicates()
    dumped = [p.describe() for p in described]
    import json

    json.dumps(dumped)  # must not raise
    freshness = next(entry for entry in dumped if entry["field"] == "valid_until")
    assert freshness["value"] == "2026-09-19"
    approval = next(entry for entry in dumped if entry["field"] == "approval_state")
    assert approval["value"] == ["approved", "draft"]


def test_exclude_injection_flagged_is_available_but_off_by_default():
    assert RetrievalFilters().exclude_injection_flagged is False
    predicate = next(
        p
        for p in RetrievalFilters(exclude_injection_flagged=True).to_predicates()
        if p.field == "injection_flag_count"
    )
    assert predicate.value == 0


def test_unknown_filter_arguments_are_a_type_error_not_silently_ignored():
    with pytest.raises(TypeError):
        RetrievalFilters(nonexistent_filter=True)  # type: ignore[call-arg]


def test_exclude_document_ids_produces_not_in_predicate():
    filters = RetrievalFilters(exclude_document_ids=["doc-1", "doc-2"])
    predicates = filters.to_predicates()
    assert len(predicates) == 1
    p = predicates[0]
    assert p.field == "id"
    assert p.op is Op.NOT_IN
    assert p.value == {"doc-1", "doc-2"}
    assert p.origin == Origin.FILTER
