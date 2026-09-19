"""Reciprocal Rank Fusion.

Pure, deterministic, and unit-tested without a database, because the whole point of
Phase 2 is that retrieval is *measurable*: if fusion is not reproducible, no
comparison between vector-only, keyword-only and hybrid means anything.

RRF is used rather than score normalisation on purpose. Cosine distances and
`ts_rank_cd` scores are not on comparable scales and their distributions shift with
the corpus, so any weighted sum of them needs re-tuning every time documents change.
Rank position does not.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class RankedList:
    """One retrieval branch's output, best first."""

    name: str
    ids: list[str]
    scores: dict[str, float] = field(default_factory=dict)
    weight: float = 1.0

    def ranks(self) -> dict[str, int]:
        """1-based rank per id, first occurrence wins."""
        out: dict[str, int] = {}
        for position, identifier in enumerate(self.ids, start=1):
            out.setdefault(identifier, position)
        return out


@dataclass
class FusedHit:
    id: str
    score: float
    ranks: dict[str, int]
    raw_scores: dict[str, float]

    def describe(self) -> dict:
        return {
            "chunk_id": self.id,
            "rrf_score": round(self.score, 6),
            "ranks": self.ranks,
            "branch_scores": {k: round(v, 6) for k, v in self.raw_scores.items()},
        }


def reciprocal_rank_fusion(
    branches: list[RankedList],
    *,
    k: int = 60,
    limit: int | None = None,
) -> list[FusedHit]:
    """Fuse ranked lists. `score = sum(weight / (k + rank))` over the branches.

    Ties are broken by: number of branches that found the id (more is better), then
    best single rank, then the id itself. The final key makes the ordering total, so
    the same inputs always produce the same output ordering.
    """
    if k <= 0:
        raise ValueError("rrf k must be positive")

    scores: dict[str, float] = {}
    ranks: dict[str, dict[str, int]] = {}
    raw: dict[str, dict[str, float]] = {}

    for branch in branches:
        for identifier, rank in branch.ranks().items():
            scores[identifier] = scores.get(identifier, 0.0) + branch.weight / (k + rank)
            ranks.setdefault(identifier, {})[branch.name] = rank
            if identifier in branch.scores:
                raw.setdefault(identifier, {})[branch.name] = branch.scores[identifier]

    hits = [
        FusedHit(
            id=identifier,
            score=score,
            ranks=ranks.get(identifier, {}),
            raw_scores=raw.get(identifier, {}),
        )
        for identifier, score in scores.items()
    ]
    hits.sort(
        key=lambda hit: (
            -hit.score,
            -len(hit.ranks),
            min(hit.ranks.values()) if hit.ranks else 10**9,
            hit.id,
        )
    )
    return hits[:limit] if limit else hits
