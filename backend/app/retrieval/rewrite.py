"""Turn follow-ups into standalone search queries and expand broad questions."""

from __future__ import annotations

import re

_FOLLOWUP = re.compile(
    r"^(what about|how about|and (the |its )?|also|pricing|price|cost|"
    r"compatibility|the same for|what if)\b",
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
    """Stitch a short follow-up onto the previous question. No model call."""
    q = question.strip()
    previous = last_user_question(history)
    if not previous:
        return q
    if looks_like_followup(q) and previous.lower() not in q.lower():
        return f"{previous} — {q}"
    return q


def expand_queries(question: str) -> list[str]:
    """One search string. Extra model calls here used to delay every answer."""
    return [question.strip()]


def keyword_overlap_score(query: str, text: str) -> float:
    terms = {t for t in re.findall(r"[a-z0-9]{3,}", query.lower())}
    if not terms:
        return 0.0
    blob = text.lower()
    hits = sum(1 for t in terms if t in blob)
    return hits / len(terms)

