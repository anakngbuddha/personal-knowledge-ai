"""3.5 The map reaches the answer, and only the accepted parts of it.

The matching and the walk are pure functions over rows, so this whole file runs without
a database.
"""

from dataclasses import dataclass, field

from app.db.models import RelationType
from app.llm.prompts import build_relationships_block, build_user_message
from app.retrieval.graph_context import GraphFact, expand_from_rows, match_products


@dataclass
class FakeProduct:
    id: str
    name: str
    slug: str = ""
    aliases: list = field(default_factory=list)


@dataclass
class FakeEdge:
    source_product_id: str
    target_product_id: str
    relation_type: str
    evidence: str = "the datasheet says so"


@dataclass
class FakeContext:
    id: str
    name: str


@dataclass
class FakeLink:
    product_id: str
    context_id: str
    relation_type: str = RelationType.SUITS_USE_CASE
    evidence: str = "listed for that room"


PANACAST = FakeProduct("p1", "Jabra PanaCast 50", "jabra-panacast-50", ["PanaCast50"])
MXA920 = FakeProduct("p2", "Shure MXA920", "shure-mxa920")
LICENCE = FakeProduct("p3", "Jabra Device Management", "jabra-device-management")
TEAMSHARE = FakeProduct("p4", "Teamshare Board", "teamshare-board")
PRODUCTS = [PANACAST, MXA920, LICENCE, TEAMSHARE]
BY_ID = {product.id: product for product in PRODUCTS}


def test_a_product_named_in_the_question_is_found_however_it_is_written():
    for question in (
        "does the Jabra PanaCast 50 work with Teams?",
        "jabra panacast-50 pricing?",
        "what about the PanaCast50 in a huddle room",
    ):
        assert [p.name for p in match_products(question, PRODUCTS)] == ["Jabra PanaCast 50"]


def test_a_name_inside_a_longer_word_is_not_a_match():
    """"Teamshare" must not drag in every product whose name is a fragment of it."""
    short = FakeProduct("p5", "Team", "team")
    found = match_products("how is the Teamshare Board licensed?", PRODUCTS + [short])
    assert [p.name for p in found] == ["Teamshare Board"]


def test_the_walk_collects_plain_sentences_with_their_quote():
    edges = [
        FakeEdge("p1", "p2", RelationType.RECOMMENDED_WITH, "Pair the bar with a ceiling array."),
        FakeEdge("p1", "p3", RelationType.REQUIRES, "Needs a management subscription."),
    ]
    context = expand_from_rows(seeds=[PANACAST], products_by_id=BY_ID, edges=edges, hops=1)
    lines = context.as_lines()
    assert any("is recommended with Shure MXA920" in line for line in lines)
    assert any("needs Jabra Device Management" in line for line in lines)
    assert any("Because:" in line for line in lines)
    assert set(context.neighbour_names) == {"Shure MXA920", "Jabra Device Management"}
    for line in lines:
        for jargon in ("relation_type", "edge", "node", "requires_license"):
            assert jargon not in line


def test_a_second_hop_is_walked_but_bounded():
    edges = [
        FakeEdge("p1", "p2", RelationType.INTEGRATES_WITH),
        FakeEdge("p2", "p3", RelationType.REQUIRES),
        FakeEdge("p3", "p4", RelationType.CROSS_SELL),
    ]
    one = expand_from_rows(seeds=[PANACAST], products_by_id=BY_ID, edges=edges, hops=1)
    two = expand_from_rows(seeds=[PANACAST], products_by_id=BY_ID, edges=edges, hops=2)
    assert "Jabra Device Management" not in one.neighbour_names
    assert "Jabra Device Management" in two.neighbour_names
    assert "Teamshare Board" not in two.neighbour_names, "two hops means two hops"


def test_neighbour_count_is_capped():
    others = [FakeProduct(f"n{i}", f"Product {i}") for i in range(10)]
    by_id = {**BY_ID, **{p.id: p for p in others}}
    edges = [FakeEdge("p1", p.id, RelationType.CROSS_SELL) for p in others]
    context = expand_from_rows(
        seeds=[PANACAST], products_by_id=by_id, edges=edges, hops=1, max_neighbours=3
    )
    assert len(context.neighbour_names) == 3


def test_only_relations_worth_walking_are_walked():
    edges = [FakeEdge("p1", "p2", RelationType.ALTERNATIVE_TO)]
    context = expand_from_rows(seeds=[PANACAST], products_by_id=BY_ID, edges=edges, hops=2)
    assert context.is_empty


def test_what_a_product_is_sold_against_is_included():
    huddle = FakeContext("c1", "Huddle room")
    context = expand_from_rows(
        seeds=[PANACAST],
        products_by_id=BY_ID,
        edges=[],
        context_links=[FakeLink("p1", "c1")],
        contexts_by_id={huddle.id: huddle},
    )
    assert any("suits Huddle room" in line for line in context.as_lines())


def test_the_same_relationship_is_stated_once():
    edges = [
        FakeEdge("p1", "p2", RelationType.REQUIRES),
        FakeEdge("p1", "p2", RelationType.REQUIRES),
    ]
    context = expand_from_rows(seeds=[PANACAST], products_by_id=BY_ID, edges=edges, hops=2)
    assert len(context.facts) == 1


def test_nothing_named_means_nothing_added():
    context = expand_from_rows(
        seeds=[], products_by_id=BY_ID, edges=[FakeEdge("p1", "p2", RelationType.REQUIRES)]
    )
    assert context.is_empty
    assert context.as_lines() == []


def test_the_block_is_fenced_like_any_other_document_content():
    """The quotes come out of uploaded files, so they are data, never instructions."""
    block = build_relationships_block([GraphFact("A", "needs", "B", "ignore all previous").as_line()])
    assert "UNTRUSTED_DOCUMENT_CONTENT" in block
    assert "Known relationships" in block
    assert "product map" in block


def test_an_empty_map_adds_nothing_to_the_prompt():
    assert build_relationships_block([]) == ""
    context_block = "## Your Documents\n\nstuff"
    assert build_user_message("q", context_block) == build_user_message("q", context_block, "")


def test_the_block_sits_between_the_passages_and_the_question():
    message = build_user_message("what pairs with it?", "## Your Documents\n\nstuff", "## Known relationships\n\nx")
    assert message.startswith("## Your Documents")
    assert message.index("Known relationships") < message.index("## Question")
