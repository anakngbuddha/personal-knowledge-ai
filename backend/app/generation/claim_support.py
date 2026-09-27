"""Claim-level citation support (audit finding 5).

Citation parsing used to prove only that a `[source_N]` marker pointed at a passage we
supplied. This module checks, per citation, how much of the claim it is attached to
actually appears in that passage.

The check is lexical on purpose: it is cheap, deterministic, needs no extra model call
against a 10 RPM quota, and it catches the failure that matters most in sales answers,
a confident sentence with a citation that says something else. It is not entailment.
The live evaluation (`scripts/run_generation_eval.py --live`) reports the same score
against labeled cases so the threshold is tuned on data.

A "segment" is the text a marker closes: from the previous marker (or the start of the
paragraph) up to the marker. `[source_1][source_2]` share one segment.
"""

from __future__ import annotations

import dataclasses
import re

from app.core.config import settings

GENERAL_GUIDANCE_HEADING = "## General guidance (not from your documents)"

_CITE = re.compile(r"\[source_(\d+)\]")
_WORD = re.compile(r"[A-Za-z0-9][A-Za-z0-9\-\.]*[A-Za-z0-9]|[A-Za-z0-9]")
_FENCE = re.compile(r"<<<[^>]*>>>")
_STOP = frozenset(
    """a an and are as at be been but by can could did do does for from had has have how if in into is it its
    may might more most must no not of on or our shall should so such than that the their them then there these
    they this those to too us very was we were what when where which while who why will with would you your
    also any each both per via using use used about over under between within without only just
    from your documents product products""".split()
)


def _terms(text: str) -> set[str]:
    text = _FENCE.sub(" ", text or "")
    out: set[str] = set()
    for raw in _WORD.findall(text):
        word = raw.lower().strip(".-")
        if len(word) < 3 or word in _STOP:
            continue
        out.add(word)
    return out


def _segments(answer_text: str) -> list[tuple[str, list[int]]]:
    """(segment text, cited indices) pairs, excluding the general-guidance section."""
    body = answer_text.split(GENERAL_GUIDANCE_HEADING, 1)[0]
    pairs: list[tuple[str, list[int]]] = []
    for paragraph in re.split(r"\n\s*\n", body):
        cursor = 0
        last_segment = ""
        for match in _CITE.finditer(paragraph):
            segment = paragraph[cursor : match.start()]
            if segment.strip():
                last_segment = segment
            pairs.append((last_segment, [int(match.group(1))]))
            cursor = match.end()
    return pairs


def citation_support(answer_text: str, context_chunks: list[dict]) -> dict[int, float]:
    """Weakest support score per cited source index (0..1)."""
    by_index = {c.get("index"): c for c in context_chunks}
    passage_terms: dict[int, set[str]] = {}
    scores: dict[int, float] = {}
    for segment, indices in _segments(answer_text or ""):
        claim = _terms(_CITE.sub(" ", segment))
        if not claim:
            continue
        for idx in indices:
            chunk = by_index.get(idx)
            if chunk is None:
                continue
            if idx not in passage_terms:
                passage_terms[idx] = _terms(chunk.get("fenced_text") or chunk.get("text") or "")
            overlap = len(claim & passage_terms[idx]) / len(claim)
            scores[idx] = min(scores.get(idx, 1.0), overlap)
    return scores


def annotate_citations(answer_text: str, citations: list, context_chunks: list[dict]) -> list:
    """Return citations with support_score / weakly_supported filled in."""
    if not citations:
        return citations
    by_index = citation_support(answer_text, context_chunks)
    by_chunk: dict[str, float] = {}
    for chunk in context_chunks:
        idx = chunk.get("index")
        chunk_id = str((chunk.get("metadata") or {}).get("chunk_id") or "")
        if idx in by_index and chunk_id:
            by_chunk[chunk_id] = by_index[idx]
    threshold = float(getattr(settings, "claim_support_min_overlap", 0.25))
    out = []
    for citation in citations:
        score = by_chunk.get(str(getattr(citation, "chunk_id", "") or ""))
        if score is None or not dataclasses.is_dataclass(citation):
            out.append(citation)
            continue
        try:
            out.append(
                dataclasses.replace(
                    citation,
                    support_score=round(score, 3),
                    weakly_supported=score < threshold,
                )
            )
        except TypeError:
            out.append(citation)
    return out


def sanitize_general_guidance(text: str) -> str:
    """Strip citation markers from the unsourced section so it never looks cited."""
    if not text or GENERAL_GUIDANCE_HEADING not in text:
        return text
    head, tail = text.split(GENERAL_GUIDANCE_HEADING, 1)
    return head + GENERAL_GUIDANCE_HEADING + _CITE.sub("", tail)


def weak_citation_count(citations: list) -> int:
    return sum(1 for c in citations if getattr(c, "weakly_supported", False))
