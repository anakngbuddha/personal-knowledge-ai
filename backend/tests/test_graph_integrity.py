"""3.2 graph integrity.

The map's vocabulary lives in three places: the Python constants, the CHECK
constraints on the tables, and the migration that moves a deployed database
forward. These tests fail the moment those three drift apart, which is the only
way a new relation type can silently become un-insertable in production.
"""
from __future__ import annotations

from app.db.migrations import MIGRATIONS
from app.db.models import (
    Base,
    CapabilityCategory,
    ContextKind,
    CurationStatus,
    EdgeStatus,
    ProductContextLink,
    ProductEdge,
    RelationType,
    SellingContext,
)

SELLING_RELATIONS = {
    "recommended_with",
    "cross_sell",
    "upsell_to",
    "certified_for",
    "requires_license",
    "bundle_component",
    "suits_use_case",
}

ORIGINAL_RELATIONS = {
    "integrates_with",
    "requires",
    "conflicts_with",
    "replaces",
    "bundles_with",
    "alternative_to",
    "migrates_to",
}


def _check_text(table, name: str) -> str:
    for constraint in table.constraints:
        if constraint.name == name:
            return str(constraint.sqltext)
    raise AssertionError(f"constraint {name} is missing from {table.name}")


def test_selling_relations_are_added_without_losing_the_old_ones():
    assert SELLING_RELATIONS <= RelationType.ALL
    assert ORIGINAL_RELATIONS <= RelationType.ALL
    assert RelationType.ALL == SELLING_RELATIONS | ORIGINAL_RELATIONS


def test_every_relation_type_is_insertable():
    clause = _check_text(ProductEdge.__table__, "ck_product_edges_relation_type")
    for relation in RelationType.ALL:
        assert f"'{relation}'" in clause, f"{relation} would be rejected by the database"


def test_relation_check_allows_nothing_extra():
    clause = _check_text(ProductEdge.__table__, "ck_product_edges_relation_type")
    quoted = {part.strip().strip("'") for part in clause.split("(", 1)[1].rstrip(")").split(",")}
    assert quoted == RelationType.ALL


def test_every_relation_type_has_plain_words():
    for relation in RelationType.ALL:
        words = RelationType.words(relation)
        assert words
        assert "_" not in words


def test_expandable_relations_are_real_relations():
    assert RelationType.EXPANDABLE <= RelationType.ALL
    assert RelationType.CONFLICTS_WITH in RelationType.EXPANDABLE
    assert RelationType.RECOMMENDED_WITH in RelationType.EXPANDABLE


def test_context_kinds_cover_use_case_room_type_and_platform():
    assert ContextKind.ALL == {"use_case", "room_type", "platform"}
    clause = _check_text(SellingContext.__table__, "ck_selling_contexts_kind")
    for kind in ContextKind.ALL:
        assert f"'{kind}'" in clause


def test_context_links_only_accept_context_shaped_relations():
    assert ProductContextLink.CONTEXT_RELATIONS <= RelationType.ALL
    clause = _check_text(
        ProductContextLink.__table__, "ck_product_context_links_relation_type"
    )
    for relation in ProductContextLink.CONTEXT_RELATIONS:
        assert f"'{relation}'" in clause
    # A product-to-product relation must not be usable against a use case.
    assert "'integrates_with'" not in clause


def test_context_links_are_reviewed_like_edges():
    clause = _check_text(ProductContextLink.__table__, "ck_product_context_links_status")
    for status in EdgeStatus.ALL:
        assert f"'{status}'" in clause
    assert ProductContextLink.__table__.c.status.default.arg == EdgeStatus.APPROVED
    assert ProductContextLink.__table__.c.is_ai_suggested.default.arg is False


def test_suggested_nodes_start_out_unconfirmed_only_when_asked():
    # A hand-made product is confirmed; 3.1 is what sets `suggested`.
    assert CurationStatus.ALL == {"confirmed", "suggested"}
    from app.db.models import Product

    assert Product.__table__.c.curation_status.default.arg == CurationStatus.CONFIRMED
    assert Product.__table__.c.is_ai_suggested.default.arg is False


def test_edges_can_cite_a_page():
    assert "page_number" in ProductEdge.__table__.c
    assert "page_number" in ProductContextLink.__table__.c


def test_new_tables_are_created_on_a_fresh_database():
    assert "selling_contexts" in Base.metadata.tables
    assert "product_context_links" in Base.metadata.tables


def test_migration_teaches_a_deployed_database_the_same_words():
    entry = next(item for item in MIGRATIONS if item[0] == "0017_selling_model")
    statements = " ".join(entry[1])
    for relation in RelationType.ALL:
        assert f"'{relation}'" in statements
    assert "CREATE TABLE IF NOT EXISTS selling_contexts" in statements
    assert "CREATE TABLE IF NOT EXISTS product_context_links" in statements
    assert "DROP CONSTRAINT IF EXISTS ck_product_edges_relation_type" in statements


def test_capability_categories_collapse_vendor_wording():
    assert CapabilityCategory.normalize("Headsets") == CapabilityCategory.HEADSETS
    assert CapabilityCategory.normalize("ceiling microphone") == CapabilityCategory.AUDIO
    assert CapabilityCategory.normalize("Huawei Cloud") == CapabilityCategory.CLOUD
    assert CapabilityCategory.normalize("4K camera") == CapabilityCategory.VIDEO
    assert CapabilityCategory.normalize("Meeting Rooms") == CapabilityCategory.CONFERENCING
    assert CapabilityCategory.normalize("") == CapabilityCategory.OTHER
    assert CapabilityCategory.normalize(None) == CapabilityCategory.OTHER
    assert CapabilityCategory.normalize("something nobody has said") == CapabilityCategory.OTHER


def test_capability_aliases_all_land_in_a_real_bucket():
    for bucket in CapabilityCategory.ALIASES.values():
        assert bucket in CapabilityCategory.ALL
