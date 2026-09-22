"""Turn follow-ups into standalone search queries and expand broad questions."""

from __future__ import annotations

import re
from app.core.logging import get_logger

logger = get_logger(__name__)

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
    if not previous:
        return q

    if looks_like_followup(q) and previous.lower() not in q.lower():
        try:
            from app.llm.factory import get_llm_provider

            provider = get_llm_provider()
            if getattr(provider, "model_id", "") == "fake-llm-v1":
                return f"{previous} — {q}"

            prompt = (
                "You are an assistant for query reformulation. Given conversation context and a follow-up question, "
                "rewrite the follow-up question into a single, fully explicit, standalone search query. "
                "Respond ONLY with the rewritten query, nothing else."
            )
            context = f"Previous user question: {previous}\nFollow-up question: {q}"
            ans = provider.generate_grounded_answer(
                context,
                [],
                system_prompt=prompt,
                history=history[-4:] if history else None,
            )
            rewritten = (ans.text or "").strip().split("\n")[0].strip('"\'')
            if rewritten and len(rewritten) > 3 and "general product knowledge" not in rewritten.lower():
                return rewritten
        except Exception:
            logger.debug("LLM query rewrite failed, falling back to heuristic", exc_info=True)

        return f"{previous} — {q}"
    return q


def expand_queries(question: str) -> list[str]:
    """2–3 sub-queries for compare / overview questions; otherwise just the question."""
    q = question.strip()
    if not _BROAD.search(q):
        return [q]

    try:
        from app.llm.factory import get_llm_provider

        provider = get_llm_provider()
        if getattr(provider, "model_id", "") != "fake-llm-v1":
            prompt = (
                "Given a broad or comparative user search query, expand it into 2 to 3 distinct, specific search sub-queries. "
                "Return each sub-query on a new line. Do not number or bullet them."
            )
            ans = provider.generate_grounded_answer(
                f"User query: {q}",
                [],
                system_prompt=prompt,
            )
            lines = [line.strip("- *123456789. ").strip() for line in (ans.text or "").split("\n") if line.strip()]
            if len(lines) >= 2 and not any("general product knowledge" in l.lower() for l in lines):
                return [q] + lines[:2]
    except Exception:
        logger.debug("LLM query expansion failed, falling back to heuristic", exc_info=True)

    return [q, f"{q} specifications compatibility", f"{q} recommended products"]


def keyword_overlap_score(query: str, text: str) -> float:
    terms = {t for t in re.findall(r"[a-z0-9]{3,}", query.lower())}
    if not terms:
        return 0.0
    blob = text.lower()
    hits = sum(1 for t in terms if t in blob)
    return hits / len(terms)

