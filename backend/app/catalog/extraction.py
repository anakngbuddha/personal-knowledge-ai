"""3.1 Read the product map out of a source.

The previous build could only find a relationship when a sentence happened to match
one of seven regular expressions and both product names were already in the catalog.
That means a brand new vendor PDF produced nothing at all, which is exactly the case
that matters: you upload a datasheet and expect the map to fill in.

This module asks the model instead. One call per source returns the products it names,
the use cases / room types / platforms it targets, and the relationships it states,
each with the sentence that says so, the page, and a confidence. Nothing is trusted:

* source text reaches the model only through ``wrap_untrusted()``, under a system
  prompt that says document content is data, never instructions;
* a relationship with no quote is dropped, because a suggestion a person cannot check
  is worse than no suggestion;
* unknown relation names are mapped onto the real vocabulary or dropped, so the map
  can never be handed a word the database would reject;
* if the call fails or the reply is not JSON, the caller falls back to the regex pass,
  which still works and still only ever proposes.

Everything produced here is a suggestion. Nodes land as ``suggested`` and edges as
``pending_review``; a person accepts them.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field

from app.core.config import settings
from app.core.logging import get_logger
from app.db.models import CapabilityCategory, ContextKind, RelationType
from app.documents.injection import SYSTEM_CONTRACT, wrap_untrusted

logger = get_logger(__name__)

GRAPH_EXTRACT_PROMPT_VERSION = "1.0.0"

#: Relations we will accept from a reply, with the wording the prompt teaches.
_RELATION_GUIDE = (
    (RelationType.INTEGRATES_WITH, "the two work together"),
    (RelationType.REQUIRES, "the first cannot be used without the second"),
    (RelationType.CONFLICTS_WITH, "they cannot be used together"),
    (RelationType.REPLACES, "the first takes over from the second"),
    (RelationType.BUNDLES_WITH, "they are sold as one package"),
    (RelationType.ALTERNATIVE_TO, "either one solves the same problem"),
    (RelationType.MIGRATES_TO, "customers move from the first to the second"),
    (RelationType.RECOMMENDED_WITH, "the vendor recommends pairing them"),
    (RelationType.CROSS_SELL, "a natural extra sale alongside the first"),
    (RelationType.UPSELL_TO, "the second is the bigger or newer option"),
    (RelationType.CERTIFIED_FOR, "the first is certified or qualified for the second"),
    (RelationType.REQUIRES_LICENSE, "the first needs a licence or subscription named by the second"),
    (RelationType.BUNDLE_COMPONENT, "the first is a part of the second"),
    (RelationType.SUITS_USE_CASE, "the first is a good fit for the second"),
)

#: Everyday phrasings a model may return instead of the exact relation name.
_RELATION_ALIASES = {
    "works with": RelationType.INTEGRATES_WITH,
    "compatible": RelationType.INTEGRATES_WITH,
    "compatible_with": RelationType.INTEGRATES_WITH,
    "interoperable_with": RelationType.INTEGRATES_WITH,
    "connects_to": RelationType.INTEGRATES_WITH,
    "supports": RelationType.INTEGRATES_WITH,
    "depends_on": RelationType.REQUIRES,
    "prerequisite": RelationType.REQUIRES,
    "needs": RelationType.REQUIRES,
    "incompatible": RelationType.CONFLICTS_WITH,
    "incompatible_with": RelationType.CONFLICTS_WITH,
    "supersedes": RelationType.REPLACES,
    "bundled_with": RelationType.BUNDLES_WITH,
    "sold_with": RelationType.BUNDLES_WITH,
    "substitute_for": RelationType.ALTERNATIVE_TO,
    "upgrade_path_to": RelationType.MIGRATES_TO,
    "recommended": RelationType.RECOMMENDED_WITH,
    "pairs_with": RelationType.RECOMMENDED_WITH,
    "accessory_for": RelationType.CROSS_SELL,
    "add_on": RelationType.CROSS_SELL,
    "upsell": RelationType.UPSELL_TO,
    "step_up_from": RelationType.UPSELL_TO,
    "certified": RelationType.CERTIFIED_FOR,
    "qualified_for": RelationType.CERTIFIED_FOR,
    "licensed_for": RelationType.REQUIRES_LICENSE,
    "requires_subscription": RelationType.REQUIRES_LICENSE,
    "part_of": RelationType.BUNDLE_COMPONENT,
    "component_of": RelationType.BUNDLE_COMPONENT,
    "included_in": RelationType.BUNDLE_COMPONENT,
    "suits": RelationType.SUITS_USE_CASE,
    "good_for": RelationType.SUITS_USE_CASE,
    "designed_for": RelationType.SUITS_USE_CASE,
}

#: Node kinds a reply may use.
_NODE_KINDS = {"product"} | ContextKind.ALL

_KIND_ALIASES = {
    "products": "product",
    "model": "product",
    "sku": "product",
    "solution": "product",
    "usecase": ContextKind.USE_CASE,
    "use case": ContextKind.USE_CASE,
    "scenario": ContextKind.USE_CASE,
    "workload": ContextKind.USE_CASE,
    "room": ContextKind.ROOM_TYPE,
    "roomtype": ContextKind.ROOM_TYPE,
    "room type": ContextKind.ROOM_TYPE,
    "space": ContextKind.ROOM_TYPE,
    "platform": ContextKind.PLATFORM,
    "ecosystem": ContextKind.PLATFORM,
    "service": ContextKind.PLATFORM,
    "cloud": ContextKind.PLATFORM,
}

GRAPH_EXTRACT_SYSTEM_PROMPT = f"""You read one sales source and write down the products it names and how they relate.

{SYSTEM_CONTRACT}

Return exactly one JSON object and nothing else. No prose before it, no prose after it.

{{
  "nodes": [
    {{"name": "...", "kind": "product|use_case|room_type|platform", "vendor": "... or null",
      "category": "audio|video|headsets|conferencing|cloud|networking|management|security|other",
      "aliases": ["..."], "quote": "the sentence that names it", "page": 1, "confidence": 0.0}}
  ],
  "relations": [
    {{"source": "product name", "target": "product or use case name",
      "target_kind": "product|use_case|room_type|platform",
      "relation": "one of the relation names below",
      "quote": "the sentence that states it", "page": 1, "confidence": 0.0}}
  ]
}}

Relation names, and what each one means:
""" + "\n".join(f"  {name:<18} {meaning}" for name, meaning in _RELATION_GUIDE) + """

Rules:
  * Only write down something the source actually says. An empty list is a correct
    answer, and a far better one than a guess.
  * Every relation must carry the quote that states it, copied from the source. No
    quote means do not include the relation.
  * `source` and `target` must be names you also listed in `nodes`.
  * Use a product's full model name as `name`, and put shorthand in `aliases`.
  * Confidence below 0.6 for anything you inferred rather than read.
  * Never invent a specification, price, certification, or compatibility claim.
"""

GRAPH_EXTRACT_REQUEST = (
    "Read the source above and list its products and relationships. Reply with the JSON object only."
)

_PUNCTUATION = re.compile(r"[^a-z0-9]+")
_SLUG_TRIM = re.compile(r"(^-+)|(-+$)")


def normalize_name(name: str) -> str:
    """Collapse a name to a comparison key.

    "Jabra PanaCast 50", "jabra panacast-50", and "JABRA  PanaCast  50." are the same
    product, and the map should not end up holding three of them.
    """

    return _PUNCTUATION.sub(" ", (name or "").strip().lower()).strip()


def slugify(name: str, *, max_length: int = 120) -> str:
    slug = _PUNCTUATION.sub("-", (name or "").strip().lower())
    slug = _SLUG_TRIM.sub("", slug)[:max_length]
    return _SLUG_TRIM.sub("", slug) or "item"


def canonical_relation(raw: str | None) -> str | None:
    """Map whatever the model said onto a relation the database will accept."""
    if not raw:
        return None
    cleaned = str(raw).strip().lower().replace(" ", "_").replace("-", "_")
    if cleaned in RelationType.ALL:
        return cleaned
    if cleaned in _RELATION_ALIASES:
        return _RELATION_ALIASES[cleaned]
    spaced = cleaned.replace("_", " ")
    if spaced in _RELATION_ALIASES:
        return _RELATION_ALIASES[spaced]
    return None


def canonical_kind(raw: str | None, *, default: str = "product") -> str:
    if not raw:
        return default
    cleaned = str(raw).strip().lower().replace("-", "_")
    if cleaned in _NODE_KINDS:
        return cleaned
    spaced = cleaned.replace("_", " ")
    return _KIND_ALIASES.get(cleaned) or _KIND_ALIASES.get(spaced) or default


@dataclass
class ExtractedNode:
    name: str
    kind: str = "product"
    vendor: str | None = None
    category: str = CapabilityCategory.OTHER
    aliases: list[str] = field(default_factory=list)
    quote: str = ""
    page: int | None = None
    confidence: float = 0.0

    @property
    def key(self) -> str:
        return normalize_name(self.name)


@dataclass
class ExtractedRelation:
    source: str
    target: str
    relation_type: str
    target_kind: str = "product"
    quote: str = ""
    page: int | None = None
    confidence: float = 0.0


@dataclass
class GraphExtraction:
    nodes: list[ExtractedNode] = field(default_factory=list)
    relations: list[ExtractedRelation] = field(default_factory=list)
    origin: str = "llm"  # llm | none
    prompt_version: str = GRAPH_EXTRACT_PROMPT_VERSION

    @property
    def is_empty(self) -> bool:
        return not self.nodes and not self.relations


def extract_graph(text: str, *, filename: str, provider=None) -> GraphExtraction:
    """Read one source. Never raises: an empty result means "fall back to the regex pass"."""
    trimmed = (text or "").strip()
    if not trimmed:
        return GraphExtraction(origin="none")

    excerpt = trimmed[: max(500, settings.graph_extract_max_chars)]
    try:
        raw = _ask_model(excerpt, filename=filename, provider=provider)
    except Exception:  # noqa: BLE001 - the map is never worth failing an upload
        logger.warning("map read: model call failed for %s", filename, exc_info=True)
        return GraphExtraction(origin="none")

    payload = _parse_json_object(raw)
    if payload is None:
        logger.info("map read: reply was not usable JSON for %s", filename)
        return GraphExtraction(origin="none")

    return parse_extraction(payload)


def parse_extraction(payload: dict) -> GraphExtraction:
    """Turn a reply into nodes and relations, dropping anything unusable."""
    nodes: dict[str, ExtractedNode] = {}
    for raw_node in _as_sequence(payload.get("nodes")):
        node = _node_from(raw_node)
        if node is None:
            continue
        existing = nodes.get(node.key)
        if existing is None:
            nodes[node.key] = node
            continue
        # Same thing named twice: keep the richer reading.
        existing.vendor = existing.vendor or node.vendor
        existing.quote = existing.quote or node.quote
        existing.page = existing.page if existing.page is not None else node.page
        existing.confidence = max(existing.confidence, node.confidence)
        for alias in node.aliases:
            if alias not in existing.aliases:
                existing.aliases.append(alias)

    relations: list[ExtractedRelation] = []
    seen: set[tuple[str, str, str]] = set()
    for raw_relation in _as_sequence(payload.get("relations")):
        relation = _relation_from(raw_relation)
        if relation is None:
            continue
        source_key = normalize_name(relation.source)
        target_key = normalize_name(relation.target)
        if source_key == target_key:
            continue
        signature = (source_key, target_key, relation.relation_type)
        if signature in seen:
            continue
        seen.add(signature)
        # A relation may name something the node list forgot; add it so the edge has
        # two ends to attach to.
        for key, name, kind in (
            (source_key, relation.source, "product"),
            (target_key, relation.target, relation.target_kind),
        ):
            if key not in nodes:
                nodes[key] = ExtractedNode(
                    name=name,
                    kind=kind,
                    quote=relation.quote,
                    page=relation.page,
                    confidence=relation.confidence,
                )
        relations.append(relation)

    return GraphExtraction(nodes=list(nodes.values()), relations=relations, origin="llm")


# -- internals --------------------------------------------------------------


def _ask_model(excerpt: str, *, filename: str, provider=None) -> str:
    if provider is None:
        from app.llm.factory import get_llm_provider

        provider = get_llm_provider()

    context_chunks = [
        {
            "index": 1,
            "fenced_text": wrap_untrusted(excerpt, source=filename),
            "citation": filename,
            "metadata": {"document_title": filename},
        }
    ]
    answer = provider.generate_grounded_answer(
        GRAPH_EXTRACT_REQUEST,
        context_chunks,
        system_prompt=GRAPH_EXTRACT_SYSTEM_PROMPT,
    )
    return answer.text or ""


def _parse_json_object(raw: str) -> dict | None:
    if not raw:
        return None
    text = raw.strip()
    if text.startswith("```"):
        text = re.sub(r"^```[a-zA-Z]*\s*", "", text)
        text = re.sub(r"```\s*$", "", text).strip()
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end <= start:
        return None
    try:
        parsed = json.loads(text[start : end + 1])
    except (ValueError, TypeError):
        return None
    return parsed if isinstance(parsed, dict) else None


def _node_from(raw) -> ExtractedNode | None:
    if isinstance(raw, str):
        name = raw.strip()
        return ExtractedNode(name=name[:255]) if name else None
    if not isinstance(raw, dict):
        return None
    name = _text(raw.get("name") or raw.get("product") or raw.get("label"))[:255]
    if not name:
        return None
    return ExtractedNode(
        name=name,
        kind=canonical_kind(raw.get("kind") or raw.get("type")),
        vendor=_text(raw.get("vendor") or raw.get("manufacturer"))[:255] or None,
        category=CapabilityCategory.normalize(_text(raw.get("category"))),
        aliases=_string_list(raw.get("aliases"), limit=6),
        quote=_text(raw.get("quote") or raw.get("evidence"))[:2000],
        page=_page(raw.get("page")),
        confidence=_confidence(raw.get("confidence")),
    )


def _relation_from(raw) -> ExtractedRelation | None:
    if not isinstance(raw, dict):
        return None
    source = _text(raw.get("source") or raw.get("from") or raw.get("subject"))[:255]
    target = _text(raw.get("target") or raw.get("to") or raw.get("object"))[:255]
    relation = canonical_relation(raw.get("relation") or raw.get("relation_type") or raw.get("type"))
    quote = _text(raw.get("quote") or raw.get("evidence"))[:2000]
    if not source or not target or not relation:
        return None
    if not quote:
        # A suggestion nobody can check is worse than no suggestion.
        return None
    return ExtractedRelation(
        source=source,
        target=target,
        relation_type=relation,
        target_kind=canonical_kind(raw.get("target_kind"), default="product"),
        quote=quote,
        page=_page(raw.get("page")),
        confidence=_confidence(raw.get("confidence")),
    )


def _as_sequence(value) -> list:
    if isinstance(value, (list, tuple)):
        return list(value)
    return []


def _text(value) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value.strip()
    return str(value).strip()


def _string_list(value, *, limit: int) -> list[str]:
    items: list[str] = []
    if isinstance(value, str):
        items = [part.strip() for part in value.split(",")]
    elif isinstance(value, (list, tuple)):
        items = [_text(part) for part in value]
    out: list[str] = []
    seen: set[str] = set()
    for item in items:
        cleaned = item.strip(" .;,")[:255]
        if not cleaned:
            continue
        key = cleaned.lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(cleaned)
        if len(out) == limit:
            break
    return out


def _page(value) -> int | None:
    try:
        page = int(value)
    except (TypeError, ValueError):
        return None
    return page if 1 <= page <= 100000 else None


def _confidence(value) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return 0.0
    return max(0.0, min(1.0, number))
