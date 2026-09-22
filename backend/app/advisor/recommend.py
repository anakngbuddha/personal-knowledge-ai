"""4.2 Advisor: the customer brief plus the product list, turned into a recommendation.

4.1 gave us a brief: what the customer actually asked for, requirement by requirement.
This module answers the question the salesperson asks next, out loud, on the call:

    "what other solutions can I add from my product list?"

The shape of the answer is fixed, because a salesperson needs the same six things
every time:

* a bundle, grouped **by requirement**, with a reason per product;
* compatibility and conflict checks read off the map, not guessed;
* what the product list cannot cover, said plainly instead of padded;
* upsell and cross-sell, which is where the deal actually grows;
* the questions still worth asking the customer;
* the assumptions a human has to verify before this goes in a proposal.

Three rules the code enforces rather than hopes for:

* **Nothing is recommended that is not in the product list.** The bundle is drawn from
  ``products``. General knowledge may explain a choice; it may never invent a SKU.
* **Every line is labelled.** A product backed by one of the user's own documents
  carries that citation. A product with nothing behind it says "general product
  knowledge" and lands in "verify before you send this".
* **Only approved relationships count.** A pending suggestion on the map is not a
  compatibility guarantee, so it is not read as one.

The whole engine is a pure function over rows (``recommend_from_rows``), so the
gap analysis, the conflict resolution and the wording are all tested without a
database, a model, or an API key.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from app.advisor.brief import CustomerBrief, RoomRequirement
from app.db.models import RelationType

ADVISOR_VERSION = "1.0.0"

#: Words that match everything and therefore mean nothing when scoring.
_STOPWORDS = frozenset(
    """
    a an and any are as at be been but by can cloud for from have has in into is it its
    more most must need needs new of on one only or other our out over per should so
    some such than that the their them then there these they this those to up use used
    using want wants we what when where which who will with would your
    """.split()
)

#: A product has to look at least this much like a requirement to be offered for it.
DEFAULT_MIN_SCORE = 2

#: Two options per requirement is a recommendation. Six is a catalogue dump.
DEFAULT_PER_REQUIREMENT = 2

#: Relations that grow the deal, and the heading each one is reported under.
_GROWTH_RELATIONS = {
    RelationType.UPSELL_TO: "upsell",
    RelationType.CROSS_SELL: "cross-sell",
    RelationType.RECOMMENDED_WITH: "cross-sell",
    RelationType.BUNDLES_WITH: "cross-sell",
}

#: How much of a document quote is worth repeating in the answer.
_QUOTE_CHARS = 200


def tokens(value: str) -> set[str]:
    """Words worth matching on: three letters or more, no stopwords."""
    found = re.findall(r"[a-z0-9][a-z0-9+./-]*", (value or "").lower())
    return {word.strip("./-") for word in found if len(word) >= 3} - _STOPWORDS


@dataclass(frozen=True)
class Citation:
    """One passage from the user's own documents, behind one recommendation."""

    label: str
    document_title: str | None = None
    quote: str = ""
    page_number: int | None = None

    def as_dict(self) -> dict:
        return {
            "label": self.label,
            "document_title": self.document_title,
            "quote": self.quote[:_QUOTE_CHARS],
            "page_number": self.page_number,
        }

    def as_phrase(self) -> str:
        where = self.document_title or self.label
        return f"{where}, page {self.page_number}" if self.page_number else str(where)


@dataclass
class Pick:
    """One product offered against one requirement."""

    product_id: str
    name: str
    vendor: str
    category: str
    slug: str = ""
    score: int = 0
    reasons: list[str] = field(default_factory=list)
    citations: list[Citation] = field(default_factory=list)

    @property
    def grounded(self) -> bool:
        """True when one of the user's own documents backs this product."""
        return bool(self.citations)

    @property
    def provenance(self) -> str:
        return "your documents" if self.grounded else "general product knowledge"

    def why(self) -> str:
        body = "; ".join(self.reasons) or f"a {self.category.lower()} option from {self.vendor}"
        if self.grounded:
            return f"{body} (from your documents: {self.citations[0].as_phrase()})"
        return f"{body} (from general product knowledge, not from a document you uploaded)"

    def as_dict(self) -> dict:
        return {
            "product_id": self.product_id,
            "name": self.name,
            "vendor": self.vendor,
            "category": self.category,
            "slug": self.slug,
            "score": self.score,
            "reasons": list(self.reasons),
            "provenance": self.provenance,
            "citations": [citation.as_dict() for citation in self.citations],
        }


@dataclass
class RequirementLine:
    """One requirement from the brief, and what the product list can do about it."""

    requirement: str
    picks: list[Pick] = field(default_factory=list)
    near_misses: list[str] = field(default_factory=list)

    @property
    def covered(self) -> bool:
        return bool(self.picks)

    def as_dict(self) -> dict:
        return {
            "requirement": self.requirement,
            "covered": self.covered,
            "products": [pick.as_dict() for pick in self.picks],
            "near_misses": list(self.near_misses),
        }


@dataclass
class Recommendation:
    """The whole answer, in the order a salesperson reads it out."""

    restated: list[str] = field(default_factory=list)
    lines: list[RequirementLine] = field(default_factory=list)
    conflicts: list[dict] = field(default_factory=list)
    also_needed: list[dict] = field(default_factory=list)
    gaps: list[str] = field(default_factory=list)
    growth: list[dict] = field(default_factory=list)
    questions: list[str] = field(default_factory=list)
    assumptions: list[str] = field(default_factory=list)
    excluded: list[dict] = field(default_factory=list)
    customer: str | None = None
    version: str = ADVISOR_VERSION

    # -- reading it ---------------------------------------------------------

    @property
    def picks(self) -> list[Pick]:
        """Every recommended product, once, in requirement order."""
        seen: set[str] = set()
        out: list[Pick] = []
        for line in self.lines:
            for pick in line.picks:
                if pick.product_id in seen:
                    continue
                seen.add(pick.product_id)
                out.append(pick)
        return out

    @property
    def is_empty(self) -> bool:
        return not self.lines and not self.gaps

    def table(self) -> tuple[list[str], list[list[str]]]:
        """The compact table: one row per recommended product."""
        headers = ["Requirement", "Product", "Vendor", "What it covers", "Backed by"]
        rows: list[list[str]] = []
        for line in self.lines:
            for pick in line.picks:
                rows.append(
                    [
                        line.requirement,
                        pick.name,
                        pick.vendor,
                        pick.category,
                        pick.citations[0].as_phrase() if pick.grounded else "General knowledge",
                    ]
                )
        return headers, rows

    def as_markdown(self) -> str:
        """Readable prose plus one compact table. Plain words only."""
        who = self.customer or "this customer"
        lines: list[str] = [f"## What {who} asked for", ""]
        if self.restated:
            lines += [f"- {item}" for item in self.restated]
        else:
            lines.append("Nothing specific was captured yet, so this is a general read.")
        lines.append("")

        lines += ["## What I would offer", ""]
        if not self.lines:
            lines += [
                "Nothing in your product list matches these requirements yet. "
                "Import your product list or add the products you sell, and ask again.",
                "",
            ]
        for line in self.lines:
            lines.append(f"**{line.requirement}**")
            lines.append("")
            for pick in line.picks:
                lines.append(f"- **{pick.name}** ({pick.vendor}) - {pick.why()}")
            lines.append("")

        headers, rows = self.table()
        if rows:
            lines += ["### At a glance", ""]
            lines.append("| " + " | ".join(headers) + " |")
            lines.append("|" + "|".join([" --- "] * len(headers)) + "|")
            for row in rows:
                lines.append("| " + " | ".join(cell.replace("|", "/") for cell in row) + " |")
            lines.append("")

        def block(title: str, items: list[str]) -> None:
            if not items:
                return
            lines.append(f"## {title}")
            lines.append("")
            lines.extend(f"- {item}" for item in items)
            lines.append("")

        block(
            "Fits and clashes",
            [
                f"{row['product']} clashes with {row['clashes_with']}: {row['reason']}"
                for row in self.conflicts
            ],
        )
        block(
            "Also needed to make this work",
            [
                f"{row['needed']} (for {row['product']})"
                + ("" if row["in_product_list"] else " - not in your product list")
                for row in self.also_needed
            ],
        )
        block("Not covered by your product list", self.gaps)
        block(
            "Worth adding to the deal",
            [f"{row['product']} - {row['kind']} of {row['from_product']}" for row in self.growth],
        )
        block(
            "Ruled out by the customer",
            [f"{row['product']} ({row['reason']})" for row in self.excluded],
        )
        block("Ask the customer", self.questions)
        block("Verify before you send this", self.assumptions)

        return "\n".join(lines).strip() + "\n"

    def as_dict(self) -> dict:
        headers, rows = self.table()
        return {
            "version": self.version,
            "customer": self.customer,
            "requirements_restated": list(self.restated),
            "recommendations": [line.as_dict() for line in self.lines],
            "conflicts": list(self.conflicts),
            "also_needed": list(self.also_needed),
            "gaps": list(self.gaps),
            "growth": list(self.growth),
            "questions_to_ask": list(self.questions),
            "assumptions_to_verify": list(self.assumptions),
            "excluded": list(self.excluded),
            "table": {"headers": headers, "rows": rows},
            "product_count": len(self.picks),
        }

    def note_title(self) -> str:
        who = self.customer or "customer"
        return f"Recommendation: {who}"[:512]


# -- the engine ------------------------------------------------------------


def recommend_from_rows(
    *,
    brief: CustomerBrief,
    products,
    edges=(),
    context_links=(),
    contexts_by_id: dict | None = None,
    capabilities_by_product: dict | None = None,
    evidence: dict | None = None,
    min_score: int = DEFAULT_MIN_SCORE,
    per_requirement: int = DEFAULT_PER_REQUIREMENT,
) -> Recommendation:
    """Rows in, recommendation out. No database, no model, no network.

    ``edges`` and ``context_links`` must already be filtered to approved rows: this
    function trusts what it is given, and the caller is the one that knows what
    "approved" means in its dialect.
    """
    contexts_by_id = contexts_by_id or {}
    capabilities_by_product = capabilities_by_product or {}
    evidence = evidence or {}

    catalogue = [product for product in products if _sellable(product)]
    kept, excluded = _apply_exclusions(catalogue, brief)

    result = Recommendation(customer=brief.customer, restated=brief.requirement_phrases())
    result.excluded = excluded

    haystacks = {
        _pid(product): _haystack(product, capabilities_by_product, contexts_by_id, context_links)
        for product in kept
    }
    by_id = {_pid(product): product for product in kept}

    # 1. requirement by requirement, what in the list looks like an answer
    for phrase in result.restated:
        line = RequirementLine(requirement=phrase)
        wanted = tokens(phrase)
        room = _room_for(phrase, brief)
        scored: list[tuple[int, list[str], object]] = []
        for product in kept:
            score, reasons = _score(product, wanted, room, haystacks[_pid(product)], brief)
            if score <= 0:
                continue
            scored.append((score, reasons, product))
        scored.sort(key=lambda item: (-item[0], str(getattr(item[2], "name", ""))))

        for score, reasons, product in scored:
            if score < min_score:
                if len(line.near_misses) < 3:
                    line.near_misses.append(str(getattr(product, "name", "")))
                continue
            if len(line.picks) >= max(1, per_requirement):
                break
            line.picks.append(_pick(product, score, reasons, evidence))

        if line.covered:
            result.lines.append(line)
        else:
            result.gaps.append(_gap_sentence(phrase, line.near_misses))

    # 2. the map decides what cannot sit in the same bundle
    result.conflicts, dropped = _resolve_conflicts(result, edges, by_id)
    for name in dropped:
        result.gaps.append(
            f"{name} was dropped from the bundle because the map says it clashes with "
            "something else in it."
        )

    # 3. prerequisites, then the things that grow the deal
    chosen_ids = {pick.product_id for pick in result.picks}
    result.also_needed = _prerequisites(chosen_ids, edges, by_id, products)
    result.growth = _growth(chosen_ids, edges, by_id, excluded)

    # 4. what to ask, and what a human still has to check
    result.questions = _questions(brief, result)
    result.assumptions = _assumptions(result)
    return result


# -- scoring ---------------------------------------------------------------


def _score(product, wanted: set[str], room, haystack: set[str], brief: CustomerBrief):
    """How well one product answers one requirement, and why, in plain words.

    A platform name is deliberately not enough on its own. Half a vendor's catalogue is
    "certified for Microsoft Teams", so matching only on "microsoft teams" would put a
    headset under "12 huddle rooms" and make the whole recommendation look careless. The
    product has to match something the customer asked for *besides* the platform, or be
    built for the room type.
    """
    platform_words = _platform_words(brief, room)
    substantive = wanted - platform_words
    overlap = substantive & haystack
    room_words = tokens(room.room_type) if room is not None else set()
    room_hit = bool(room_words & haystack)

    if not overlap and not room_hit:
        return 0, []

    score = len(overlap)
    reasons: list[str] = []
    if overlap:
        reasons.append(f"matches what they asked for ({', '.join(sorted(overlap)[:4])})")

    if room is not None:
        if room_hit:
            score += 2
            reasons.append(f"built for a {room.room_type}")
        platform = room.platform or ""
        if platform and tokens(platform) & haystack:
            score += 2
            reasons.append(f"certified for {platform}")

    for platform in brief.platforms:
        if tokens(platform) & haystack and not any("certified for" in item for item in reasons):
            score += 1
            reasons.append(f"works on {platform}")
            break

    deployment = (getattr(product, "deployment_model", "") or "").lower()
    if brief.cloud_needs and deployment in {"cloud", "hybrid"} and overlap:
        score += 1

    return score, reasons


def _platform_words(brief: CustomerBrief, room) -> set[str]:
    words: set[str] = set()
    for platform in brief.platforms:
        words |= tokens(platform)
    if room is not None and room.platform:
        words |= tokens(room.platform)
    return words


def _haystack(product, capabilities_by_product, contexts_by_id, context_links) -> set[str]:
    parts = [
        str(getattr(product, "name", "")),
        str(getattr(product, "vendor", "")),
        str(getattr(product, "category", "")),
        str(getattr(product, "description", "") or ""),
        str(getattr(product, "tier", "") or ""),
        str(getattr(product, "deployment_model", "") or ""),
    ]
    parts += [str(name) for name in capabilities_by_product.get(_pid(product), [])]
    for link in context_links:
        if str(getattr(link, "product_id", "")) != _pid(product):
            continue
        context = contexts_by_id.get(getattr(link, "context_id", None))
        if context is not None:
            parts.append(str(getattr(context, "name", "")))
    return tokens(" ".join(parts))


def _pick(product, score: int, reasons: list[str], evidence: dict) -> Pick:
    slug = str(getattr(product, "slug", "") or "")
    found = evidence.get(_pid(product)) or evidence.get(slug) or []
    citations = [item for item in found if isinstance(item, Citation)][:2]
    return Pick(
        product_id=_pid(product),
        name=str(getattr(product, "name", "")),
        vendor=str(getattr(product, "vendor", "")),
        category=str(getattr(product, "category", "")),
        slug=slug,
        score=score,
        reasons=reasons,
        citations=citations,
    )


# -- the map ---------------------------------------------------------------


def _resolve_conflicts(result: Recommendation, edges, by_id) -> tuple[list[dict], list[str]]:
    """Refuse a bundle that clashes with itself, keeping the better-matched product."""
    picks = {pick.product_id: pick for pick in result.picks}
    conflicts: list[dict] = []
    dropped: dict[str, str] = {}

    for edge in edges:
        if getattr(edge, "relation_type", "") != RelationType.CONFLICTS_WITH:
            continue
        left, right = _ends(edge)
        if left not in picks or right not in picks:
            continue
        if left in dropped or right in dropped:
            continue
        loser = left if picks[left].score <= picks[right].score else right
        winner = right if loser == left else left
        reason = (getattr(edge, "evidence", "") or "the map records a clash").strip()
        conflicts.append(
            {
                "product": picks[winner].name,
                "clashes_with": picks[loser].name,
                "reason": reason[:_QUOTE_CHARS],
                "dropped": picks[loser].name,
            }
        )
        dropped[loser] = picks[loser].name

    if dropped:
        for line in result.lines:
            line.picks = [pick for pick in line.picks if pick.product_id not in dropped]
        result.lines = [line for line in result.lines if line.covered]
    return conflicts, list(dropped.values())


def _prerequisites(chosen_ids: set[str], edges, by_id, all_products) -> list[dict]:
    """What the bundle needs that the bundle does not already contain."""
    known = {_pid(product) for product in all_products}
    out: list[dict] = []
    seen: set[tuple[str, str]] = set()
    for edge in edges:
        relation = getattr(edge, "relation_type", "")
        if relation not in {RelationType.REQUIRES, RelationType.REQUIRES_LICENSE}:
            continue
        source, target = _pid_of(edge, "source_product_id"), _pid_of(edge, "target_product_id")
        if source not in chosen_ids or target in chosen_ids:
            continue
        key = (source, target)
        if key in seen:
            continue
        seen.add(key)
        needed = by_id.get(target)
        out.append(
            {
                "product": str(getattr(by_id.get(source), "name", source)),
                "needed": str(getattr(needed, "name", "")) or "a prerequisite not on the map",
                "relation": RelationType.words(relation),
                "in_product_list": target in known,
                "evidence": (getattr(edge, "evidence", "") or "")[:_QUOTE_CHARS],
            }
        )
    return out


def _growth(chosen_ids: set[str], edges, by_id, excluded: list[dict]) -> list[dict]:
    """Upsell and cross-sell, drawn only from the product list and never from an exclusion."""
    ruled_out = {str(row.get("product", "")).lower() for row in excluded}
    out: list[dict] = []
    seen: set[str] = set()
    for edge in edges:
        kind = _GROWTH_RELATIONS.get(getattr(edge, "relation_type", ""))
        if kind is None:
            continue
        source, target = _pid_of(edge, "source_product_id"), _pid_of(edge, "target_product_id")
        if source not in chosen_ids or target in chosen_ids or target in seen:
            continue
        candidate = by_id.get(target)
        if candidate is None or str(getattr(candidate, "name", "")).lower() in ruled_out:
            continue
        seen.add(target)
        out.append(
            {
                "product": str(getattr(candidate, "name", "")),
                "vendor": str(getattr(candidate, "vendor", "")),
                "kind": kind,
                "from_product": str(getattr(by_id.get(source), "name", source)),
                "evidence": (getattr(edge, "evidence", "") or "")[:_QUOTE_CHARS],
            }
        )
    return out


# -- what is still missing -------------------------------------------------


def _questions(brief: CustomerBrief, result: Recommendation) -> list[str]:
    out: list[str] = []
    if not brief.budget:
        out.append("What budget range are we working to?")
    if not brief.timeline:
        out.append("When do they need this live?")
    if not brief.platforms:
        out.append("Which meeting platform are they standardising on: Teams, Zoom, or Webex?")
    for room in brief.rooms:
        if room.count is None and room.seats is None:
            out.append(f"How many {room.room_type}s are we fitting out?")
        if room.platform is None and brief.platforms:
            out.append(f"Is the {room.room_type} on the same platform as the rest?")
    if brief.cloud_needs and not brief.size:
        out.append("How much data are we protecting, and what recovery time do they expect?")
    if result.gaps:
        out.append("Are they open to a product we would have to source for this?")
    if not brief.exclusions:
        out.append("Is there any vendor they have already ruled out?")

    deduped: list[str] = []
    for question in out:
        if question not in deduped:
            deduped.append(question)
    return deduped[:8]


def _assumptions(result: Recommendation) -> list[str]:
    out: list[str] = []
    ungrounded = [pick.name for pick in result.picks if not pick.grounded]
    if ungrounded:
        out.append(
            "These come from general product knowledge, not from a document you uploaded, so "
            "confirm specs and pricing with the vendor: " + ", ".join(sorted(ungrounded)[:8]) + "."
        )
    if result.also_needed:
        missing = [row["needed"] for row in result.also_needed if not row["in_product_list"]]
        if missing:
            out.append(
                "These prerequisites are not in your product list and will need sourcing or "
                "confirming: " + ", ".join(sorted(set(missing))[:8]) + "."
            )
    if not result.conflicts:
        out.append(
            "No clashes were found on your product map. That is only as complete as the map, so "
            "sanity-check compatibility for anything the customer already owns."
        )
    out.append("No prices or discounts are included here. Quote from your current price list.")
    return out


def _gap_sentence(phrase: str, near_misses: list[str]) -> str:
    if near_misses:
        return (
            f"{phrase}: nothing in your product list is a close enough match. "
            f"Closest: {', '.join(near_misses)}."
        )
    return f"{phrase}: nothing in your product list covers this."


# -- small helpers ---------------------------------------------------------


def _sellable(product) -> bool:
    """A suggestion, a sample, or an end-of-life product is not something to quote."""
    if getattr(product, "is_demo", False):
        return False
    if (getattr(product, "lifecycle_status", "GA") or "GA") == "EOL":
        return False
    curation = getattr(product, "curation_status", "confirmed") or "confirmed"
    return curation != "suggested"


def _apply_exclusions(products, brief: CustomerBrief):
    """Drop whatever the customer ruled out, and say which rule dropped it."""
    rules = [str(item).strip().lower() for item in brief.exclusions if str(item).strip()]
    if not rules:
        return list(products), []
    kept, excluded = [], []
    for product in products:
        haystack = " ".join(
            [
                str(getattr(product, "name", "")),
                str(getattr(product, "vendor", "")),
                str(getattr(product, "deployment_model", "") or ""),
            ]
        ).lower()
        hit = next((rule for rule in rules if rule and rule in haystack), None)
        if hit:
            excluded.append(
                {
                    "product": str(getattr(product, "name", "")),
                    "vendor": str(getattr(product, "vendor", "")),
                    "reason": f"the customer ruled out {hit}",
                }
            )
        else:
            kept.append(product)
    return kept, excluded


def _room_for(phrase: str, brief: CustomerBrief) -> RoomRequirement | None:
    for room in brief.rooms:
        if room.as_phrase() == phrase:
            return room
    return None


def _pid(product) -> str:
    return str(getattr(product, "id", "") or getattr(product, "slug", ""))


def _pid_of(edge, attribute: str) -> str:
    return str(getattr(edge, attribute, "") or "")


def _ends(edge) -> tuple[str, str]:
    return _pid_of(edge, "source_product_id"), _pid_of(edge, "target_product_id")
