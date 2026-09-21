"""Turn follow-ups into standalone search queries and expand broad questions."""

from __future__ import annotations

import re

_FOLLOWUP = re.compile(
    r"^(what about|how about|and (the |its )?|also|pricing|price|cost|"
    r"compatibility|the same for|what if)\b",
    re.I,
)
_BROAD = re.compile(
    r"\b(compare|versus|vs\.?|difference|overview|summarize|summary|which)\b",
    re.I,
)


def last_user_question(history: list[dict] | None) -> str | None:
    if not history:
        return None
    for turn in reversed(history):
        if turn.get("role") == "user" and str(turn.get("content") or "").strip():
            return str(turn["content"]).strip()
    return None


def looks_like_followup(question: str) -> bool:
    text = question.strip()
    if len(text.split()) <= 6:
        return True
    return bool(_FOLLOWUP.search(text))


def rewrite_query(question: str, history: list[dict] | None = None) -> str:
    """Make a follow-up searchable without the rest of the conversation."""
    q = question.strip()
    previous = last_user_question(history)
    if previous and looks_like_followup(q) and previous.lower() not in q.lower():
        return f"{previous} — {q}"
    return q


def expand_queries(question: str) -> list[str]:
    """2–3 sub-queries for compare / overview questions; otherwise just the question."""
    q = question.strip()
    if not _BROAD.search(q):
        return [q]
    return [q, f"{q} specifications compatibility", f"{q} recommended products"]


def keyword_overlap_score(query: str, text: str) -> float:
    terms = {t for t in re.findall(r"[a-z0-9]{3,}", query.lower())}
    if not terms:
        return 0.0
    blob = text.lower()
    hits = sum(1 for t in terms if t in blob)
    return hits / len(terms)
