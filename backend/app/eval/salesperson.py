"""Salesperson-style generation quality checks (PART2 Phase 6.1).

Heuristic scorers for fake-provider offline evals. Checks readable prose,
provenance labels, catalog grounding, and empty-retrieval behavior.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

_JARGON = (
    "chunk",
    "ingest",
    "mcp",
    "rls",
    "dossier",
    "ledger",
    "collateral",
    "hybrid search",
    "pgvector",
)

_PROVENANCE_PHRASES = (
    "from your documents",
    "from your product map",
    "from general product knowledge",
    "from the web",
    "no matching documents",
)

_PRODUCT_NAME_RE = re.compile(
    r"\b(?:Jabra|Shure|Poly|Huawei|Apex|Aegis|Nova|QuantumBook)[\w\s\-]{0,40}",
    re.IGNORECASE,
)


@dataclass
class SalespersonScore:
    case_id: str
    passed: bool
    failures: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {
            "id": self.case_id,
            "passed": self.passed,
            "failures": self.failures,
        }


def score_prose(text: str) -> list[str]:
    """Fail if answer is empty, tiny, or uses forbidden technical jargon."""
    failures: list[str] = []
    body = (text or "").strip()
    if len(body) < 40:
        failures.append("answer too short for readable prose")
    lowered = body.lower()
    for term in _JARGON:
        if term in lowered:
            failures.append(f"jargon: {term}")
    return failures


def score_provenance(text: str, *, require: bool) -> list[str]:
    if not require:
        return []
    lowered = (text or "").lower()
    if any(phrase in lowered for phrase in _PROVENANCE_PHRASES):
        return []
    return ["missing provenance label"]


def score_catalog_grounding(text: str, allowed_products: list[str]) -> list[str]:
    """Flag product-like names that are not in the allowed fixture catalog."""
    if not allowed_products:
        return []
    allowed = {name.lower() for name in allowed_products}
    failures: list[str] = []
    for match in _PRODUCT_NAME_RE.finditer(text or ""):
        name = " ".join(match.group(0).split())
        # Allow short vendor-only mentions when a product from that vendor is allowed.
        vendors = {p.split()[0].lower() for p in allowed if p.split()}
        first = name.split()[0].lower() if name.split() else ""
        if name.lower() in allowed or first in vendors:
            continue
        # Exact-ish: any allowed product contained in the match or vice versa
        if any(a in name.lower() or name.lower() in a for a in allowed):
            continue
        failures.append(f"fabricated product: {name}")
    return failures


def score_empty_retrieval(
    text: str,
    *,
    refused: bool,
    mode: str,
) -> list[str]:
    """Expert must answer with a label; strict must refuse politely."""
    failures: list[str] = []
    lowered = (text or "").lower()
    if mode == "expert":
        if refused:
            failures.append("expert mode refused on empty retrieval")
        if "no matching documents" not in lowered and "general product knowledge" not in lowered:
            failures.append("expert empty-retrieval missing provenance")
        if "upload" not in lowered:
            failures.append("expert empty-retrieval missing upload suggestion")
    elif mode == "strict":
        if not refused and "insufficient" not in lowered and "do not contain" not in lowered:
            failures.append("strict mode did not refuse on empty retrieval")
        if refused and len((text or "").strip()) < 20:
            failures.append("strict refusal too curt")
    return failures


def score_salesperson_case(
    case: dict[str, Any],
    *,
    text: str,
    refused: bool,
) -> SalespersonScore:
    checks = case.get("checks") or {}
    failures: list[str] = []

    if checks.get("prose", True):
        failures.extend(score_prose(text))
    if checks.get("provenance"):
        failures.extend(score_provenance(text, require=True))
    allowed = case.get("allowed_products") or []
    if checks.get("no_fabricated_specs", bool(allowed)):
        failures.extend(score_catalog_grounding(text, allowed))
    empty_mode = checks.get("empty_retrieval")
    if empty_mode:
        failures.extend(score_empty_retrieval(text, refused=refused, mode=str(empty_mode)))

    must_contain = case.get("must_contain") or []
    lowered = (text or "").lower()
    for needle in must_contain:
        if str(needle).lower() not in lowered:
            failures.append(f"missing expected phrase: {needle}")

    return SalespersonScore(
        case_id=str(case.get("id") or ""),
        passed=not failures,
        failures=failures,
    )
