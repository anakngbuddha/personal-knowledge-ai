"""Reciprocal Rank Fusion. Determinism is the requirement, not a nicety: the Phase 2
baseline comparison is meaningless if fusion output can vary between runs."""

import math

import pytest

from app.retrieval.fusion import RankedList, reciprocal_rank_fusion


def branches():
    vector = RankedList("vector", ["a", "b", "c", "d"], {"a": 0.91, "b": 0.88, "c": 0.70, "d": 0.50})
    keyword = RankedList("keyword", ["c", "a", "e"], {"c": 0.44, "a": 0.31, "e": 0.12})
    return [vector, keyword]


def test_score_is_the_rrf_formula():
    hits = reciprocal_rank_fusion(branches(), k=60)
    top = hits[0]
    assert top.id == "a"
    assert math.isclose(top.score, 1 / 61 + 1 / 62)
    assert top.ranks == {"vector": 1, "keyword": 2}
    assert top.raw_scores == {"vector": 0.91, "keyword": 0.31}


def test_agreement_beats_a_single_strong_rank():
    """`c` is only 3rd on vector but 1st on keyword, so it outranks `b` which is 2nd on
    vector and absent from keyword. That is the whole point of fusing ranks."""
    order = [hit.id for hit in reciprocal_rank_fusion(branches(), k=60)]
    assert order.index("c") < order.index("b")


def test_result_is_the_union_of_branches():
    order = [hit.id for hit in reciprocal_rank_fusion(branches(), k=60)]
    assert set(order) == {"a", "b", "c", "d", "e"}


def test_deterministic_across_runs_and_branch_order():
    first = [hit.id for hit in reciprocal_rank_fusion(branches(), k=60)]
    second = [hit.id for hit in reciprocal_rank_fusion(branches(), k=60)]
    reversed_branches = [hit.id for hit in reciprocal_rank_fusion(branches()[::-1], k=60)]
    assert first == second == reversed_branches


def test_total_ordering_on_a_perfect_tie():
    one = RankedList("x", ["z", "y"])
    two = RankedList("w", ["y", "z"])
    assert [hit.id for hit in reciprocal_rank_fusion([one, two], k=60)] == ["y", "z"]


def test_single_branch_degrades_to_that_branch_order():
    vector = branches()[0]
    assert [hit.id for hit in reciprocal_rank_fusion([vector], k=60)] == vector.ids


def test_k_changes_how_flat_the_curve_is():
    small = reciprocal_rank_fusion(branches(), k=1)
    large = reciprocal_rank_fusion(branches(), k=1000)
    assert small[0].score > large[0].score
    spread_small = small[0].score - small[-1].score
    spread_large = large[0].score - large[-1].score
    assert spread_small > spread_large


def test_limit_and_validation():
    assert len(reciprocal_rank_fusion(branches(), k=60, limit=2)) == 2
    assert reciprocal_rank_fusion([], k=60) == []
    with pytest.raises(ValueError):
        reciprocal_rank_fusion(branches(), k=0)


def test_duplicate_ids_in_one_branch_keep_the_best_rank():
    duplicated = RankedList("vector", ["a", "b", "a"])
    hits = reciprocal_rank_fusion([duplicated], k=60)
    assert [hit.id for hit in hits] == ["a", "b"]
    assert hits[0].ranks["vector"] == 1
