"""Collateral metadata: safe defaults, explicit gaps, and a real promotion gate."""

import pytest
from pydantic import ValidationError

from app.documents.metadata import DocumentMetadataIn


def test_defaults_are_safe_never_permissive():
    meta = DocumentMetadataIn()
    assert meta.sensitivity == "internal"  # not public
    assert meta.approval_state == "draft"  # not approved
    assert meta.ownership == "unknown"  # not own


def test_unfilled_curation_fields_are_reported_not_invented():
    meta = DocumentMetadataIn()
    assert set(meta.missing_fields()) == {
        "vendor",
        "ownership",
        "products_referenced",
        "valid_until",
    }
    assert meta.is_complete is False


def test_a_resold_document_needs_its_upstream_source_of_truth():
    """Phase 9's vendor-collateral monitoring has nothing to re-check without it."""
    meta = DocumentMetadataIn(
        vendor="Northwind",
        ownership="resold",
        products_referenced=["VaultStore"],
        valid_until="2027-01-31",
    )
    assert meta.missing_fields() == ["source_of_truth_url"]
    complete = DocumentMetadataIn(
        vendor="Northwind",
        ownership="resold",
        products_referenced=["VaultStore"],
        valid_until="2027-01-31",
        source_of_truth_url="https://northwind.example.com/vaultstore",
    )
    assert complete.is_complete


def test_incomplete_metadata_cannot_be_approved_when_auto_approve_is_off(monkeypatch):
    from app.core.config import settings

    monkeypatch.setattr(settings, "auto_approve_uploads", False)
    meta = DocumentMetadataIn(approval_state="approved")
    error = meta.promotion_error()
    assert error and "cannot approve" in error
    assert "vendor" in error


def test_auto_approve_allows_incomplete_metadata():
    from app.core.config import settings

    # Default for single-owner mode is auto-approve.
    assert settings.auto_approve_uploads is True
    meta = DocumentMetadataIn(approval_state="approved")
    assert meta.promotion_error() is None
    assert meta.is_complete is False


def test_complete_metadata_can_be_approved(monkeypatch):
    from app.core.config import settings

    monkeypatch.setattr(settings, "auto_approve_uploads", False)
    meta = DocumentMetadataIn(
        vendor="Us",
        ownership="own",
        products_referenced=["OrbitCloud"],
        valid_until="2027-06-30",
        approval_state="approved",
    )
    assert meta.promotion_error() is None


def test_products_accept_a_comma_separated_string_from_a_form_post():
    meta = DocumentMetadataIn(products_referenced="OrbitCloud, VaultStore ,, ")
    assert meta.products_referenced == ["OrbitCloud", "VaultStore"]


def test_blank_strings_become_none_so_they_count_as_missing():
    meta = DocumentMetadataIn(vendor="   ", title="")
    assert meta.vendor is None
    assert meta.title is None


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("sensitivity", "publik"),
        ("approval_state", "aproved"),
        ("ownership", "rented"),
        ("source_type", "fax"),
    ],
)
def test_a_typo_in_a_label_is_rejected_not_coerced(field, value):
    """Silently mapping an unknown label onto a default is how confidential material
    ends up labelled `public`."""
    with pytest.raises(ValidationError):
        DocumentMetadataIn(**{field: value})


def test_unknown_metadata_keys_are_rejected():
    with pytest.raises(ValidationError):
        DocumentMetadataIn(sensitivty="internal")  # typo in the key itself
