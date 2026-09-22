"""2.2 Understand step: read each new source once, then remember what it says.

After extraction and before the document is marked ready, one model call turns the raw
text into a small structured record: what kind of document it is, which vendors and
products it names, which version or validity date it carries, a short summary, key
facts, and tags. That record is what makes "what did I just upload?" answerable, and
what lets overview questions use per-document summaries instead of stray chunks.

Three properties matter more than cleverness:

* **Containment.** Source text reaches the model only through ``wrap_untrusted()``, the
  same fence the answer path uses, under a system prompt that says document content is
  data. A datasheet cannot instruct the summarizer.
* **Ingestion never fails here.** If the model returns prose instead of JSON, or the
  call raises, a deterministic heuristic fills the same fields. A source that could not
  be summarized is still searchable, which is the whole point of uploading it.
* **Deterministic in tests.** The heuristic is pure string processing, and the fake
  provider does not emit JSON, so the offline suite exercises the fallback path without
  a network call or a fixture file.

Only a high-confidence model result is allowed to auto-fill vendor, products, and
``valid_until``. The heuristic deliberately reports low confidence, so a guess never
silently becomes curated metadata. Everything stays editable in the source panel.

The summarizer prompt is versioned separately from the answer prompt
(``UNDERSTAND_PROMPT_VERSION``), so tuning a summary does not invalidate the answer
evals.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from datetime import date, datetime, timezone

from app.core.config import settings
from app.core.logging import get_logger
from app.documents.injection import SYSTEM_CONTRACT, wrap_untrusted

logger = get_logger(__name__)

UNDERSTAND_PROMPT_VERSION = "1.0.0"

UNDERSTAND_SYSTEM_PROMPT = f"""You catalogue one uploaded sales source for a salesperson.

{SYSTEM_CONTRACT}

Return exactly one JSON object and nothing else. No prose before it, no prose after it.

Keys:
  doc_type        one of: datasheet, pricing, proposal, rfp, quote, guide, case_study,
                  compatibility_matrix, release_notes, contract, notes, other
  vendors         list of vendor or manufacturer names actually named in the source
  products        list of product or model names actually named in the source
  version_label   version, revision, or edition string if the source carries one, else null
  valid_until     YYYY-MM-DD if the source states an expiry, price validity, or renewal
                  date, else null
  summary         5 to 8 sentences a salesperson could read before a customer call
  key_facts       list of objects with a "label" and a "value", at most 8, only facts
                  stated in the source
  tags            list of short lowercase topic tags, at most 8
  confidence      0.0 to 1.0, how sure you are about vendors, products, and dates

Rules:
  * Never invent a vendor, product, specification, price, or date. An empty list is a
    correct answer.
  * If the text is too thin to describe, return a low confidence and an honest summary
    that says so.
  * Report confidence below 0.5 whenever the vendors or products are inferred rather
    than written down.
"""

UNDERSTAND_REQUEST = "Catalogue the source above. Reply with the JSON object only."

_DOC_TYPES = {
    "datasheet",
    "pricing",
    "proposal",
    "rfp",
    "quote",
    "guide",
    "case_study",
    "compatibility_matrix",
    "release_notes",
    "contract",
    "notes",
    "other",
}

# Filename and body hints for the offline reader, most specific first.
_TYPE_HINTS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("compatibility_matrix", ("compatibility", "interop", "certified for")),
    ("release_notes", ("release notes", "changelog", "what's new")),
    ("pricing", ("price list", "pricing", "msrp", "list price")),
    ("quote", ("quotation", "quote no", "quote #")),
    ("rfp", ("request for proposal", "rfp", "tender")),
    ("proposal", ("proposal", "statement of work", "scope of work")),
    ("contract", ("master service", "agreement", "terms and conditions")),
    ("case_study", ("case study", "success story")),
    ("guide", ("deployment guide", "admin guide", "installation", "user guide")),
    ("datasheet", ("datasheet", "data sheet", "spec sheet", "specifications")),
)

_TAG_VOCABULARY: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("pricing", ("price", "pricing", "discount", "msrp")),
    ("licensing", ("license", "licence", "subscription", "seat")),
    ("compatibility", ("compatible", "certified", "interoperab", "supported with")),
    ("security", ("encryption", "security", "soc 2", "iso 27001")),
    ("support", ("warranty", "support", "sla", "rma")),
    ("installation", ("install", "mounting", "deployment", "provisioning")),
    ("audio", ("microphone", "speaker", "audio", "dsp")),
    ("video", ("camera", "video", "display", "ptz")),
    ("conferencing", ("conference", "meeting room", "huddle", "teams room", "zoom room")),
    ("headsets", ("headset", "earbud", "ear cushion")),
    ("cloud", ("cloud", "saas", "tenant", "region")),
)

_LABEL_LINE = re.compile(r"^\s*([A-Z][A-Za-z0-9 /&()'-]{2,40})\s*[:\u2013-]\s*(\S.{0,160})$")
_VERSION = re.compile(
    r"\b(?:version|ver\.?|rev(?:ision)?|release|edition)\s*[:.]?\s*([A-Za-z]?\d+(?:\.\d+){0,3})\b",
    re.IGNORECASE,
)
_ISO_DATE = re.compile(r"\b(\d{4})-(\d{2})-(\d{2})\b")
_VALID_UNTIL = re.compile(
    r"(?:valid(?:\s+un)?til|expires?(?:\s+on)?|renewal date|quote valid until)\s*[:\s]\s*(\d{4}-\d{2}-\d{2})",
    re.IGNORECASE,
)
_VENDOR_LABEL = re.compile(
    r"^\s*(?:vendor|manufacturer|brand|supplier|oem)\s*[:\u2013-]\s*(\S.{0,80})$",
    re.IGNORECASE | re.MULTILINE,
)
_PRODUCT_LABEL = re.compile(
    r"^\s*(?:product|model|part(?:\s+number)?|sku|solution)\s*[:\u2013-]\s*(\S.{0,80})$",
    re.IGNORECASE | re.MULTILINE,
)
_SENTENCE_SPLIT = re.compile(r"(?<=[.!?])\s+")


@dataclass
class SourceUnderstanding:
    """What one pass over a source produced. Every field is optional by design."""

    doc_type: str | None = None
    vendors: list[str] = field(default_factory=list)
    products: list[str] = field(default_factory=list)
    version_label: str | None = None
    valid_until: date | None = None
    summary: str = ""
    key_facts: list[dict] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)
    confidence: float = 0.0
    origin: str = "heuristic"  # llm | heuristic
    prompt_version: str = UNDERSTAND_PROMPT_VERSION

    @property
    def is_confident(self) -> bool:
        return self.confidence >= settings.understanding_min_confidence

    def as_dict(self) -> dict:
        return {
            "doc_type": self.doc_type,
            "vendors": list(self.vendors),
            "products": list(self.products),
            "version_label": self.version_label,
            "valid_until": self.valid_until.isoformat() if self.valid_until else None,
            "summary": self.summary,
            "key_facts": list(self.key_facts),
            "tags": list(self.tags),
            "confidence": self.confidence,
            "origin": self.origin,
            "prompt_version": self.prompt_version,
        }


def understand_source(text: str, *, filename: str, provider=None) -> SourceUnderstanding:
    """Describe one source. Always returns something; never raises."""
    trimmed = (text or "").strip()
    if not trimmed:
        return SourceUnderstanding(
            doc_type="other",
            summary="This source had no readable text.",
            confidence=0.0,
            origin="heuristic",
        )

    excerpt = trimmed[: max(500, settings.understanding_max_chars)]

    if settings.document_understanding_enabled:
        try:
            raw = _ask_model(excerpt, filename=filename, provider=provider)
            payload = _parse_json_object(raw)
            if payload is not None:
                understanding = _from_payload(payload)
                if understanding is not None:
                    return understanding
            logger.info(
                "understand: model reply was not usable JSON for %s; using the offline reader",
                filename,
            )
        except Exception:  # noqa: BLE001 - a summary is never worth failing an upload
            logger.warning("understand: model call failed for %s", filename, exc_info=True)

    return heuristic_understanding(excerpt, filename=filename)


def _ask_model(excerpt: str, *, filename: str, provider=None) -> str:
    if provider is None:
        from app.llm.factory import get_llm_provider

        provider = get_llm_provider()

    fenced = wrap_untrusted(excerpt, source=filename)
    context_chunks = [
        {
            "index": 1,
            "fenced_text": fenced,
            "citation": filename,
            "metadata": {"document_title": filename},
        }
    ]
    answer = provider.generate_grounded_answer(
        UNDERSTAND_REQUEST,
        context_chunks,
        system_prompt=UNDERSTAND_SYSTEM_PROMPT,
    )
    return answer.text or ""


def _parse_json_object(raw: str) -> dict | None:
    """Pull the first JSON object out of a reply, fenced or bare."""
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


def _from_payload(payload: dict) -> SourceUnderstanding | None:
    summary = _as_text(payload.get("summary"))
    doc_type = _as_text(payload.get("doc_type")).lower().replace(" ", "_") or None
    if doc_type is not None and doc_type not in _DOC_TYPES:
        doc_type = "other"
    if not summary and not doc_type:
        return None
    return SourceUnderstanding(
        doc_type=doc_type,
        vendors=_as_list(payload.get("vendors"), limit=8),
        products=_as_list(payload.get("products"), limit=20),
        version_label=_as_text(payload.get("version_label"))[:128] or None,
        valid_until=_as_date(payload.get("valid_until")),
        summary=summary[:4000],
        key_facts=_as_facts(payload.get("key_facts")),
        tags=[t.lower() for t in _as_list(payload.get("tags"), limit=8)],
        confidence=_as_confidence(payload.get("confidence")),
        origin="llm",
    )


def heuristic_understanding(text: str, *, filename: str) -> SourceUnderstanding:
    """Deterministic offline reader. Same fields, honest low confidence."""
    lowered = text.lower()
    name = (filename or "").lower()

    doc_type = "other"
    # The filename is the author's label. A datasheet that mentions "certified for"
    # is still a datasheet; body hints only fill in when the name is silent.
    for candidate, hints in _TYPE_HINTS:
        if any(hint in name for hint in hints):
            doc_type = candidate
            break
    if doc_type == "other":
        for candidate, hints in _TYPE_HINTS:
            if any(hint in lowered for hint in hints):
                doc_type = candidate
                break

    vendors = _unique(_VENDOR_LABEL.findall(text))[:4]
    products = _unique(_PRODUCT_LABEL.findall(text))[:10]

    version_match = _VERSION.search(text)
    version_label = version_match.group(1) if version_match else None

    valid_until = None
    valid_match = _VALID_UNTIL.search(text)
    if valid_match:
        valid_until = _as_date(valid_match.group(1))

    tags = [tag for tag, hints in _TAG_VOCABULARY if any(hint in lowered for hint in hints)]
    if doc_type != "other":
        tags = [doc_type.replace("_", " ")] + tags

    return SourceUnderstanding(
        doc_type=doc_type,
        vendors=vendors,
        products=products,
        version_label=version_label,
        valid_until=valid_until,
        summary=_lead_summary(text),
        key_facts=_label_facts(text),
        tags=tags[:8],
        # Deliberately below the auto-fill threshold: a regex guess must never become
        # curated metadata on its own.
        confidence=0.35,
        origin="heuristic",
    )


def apply_understanding(document, understanding: SourceUnderstanding) -> None:
    """Write the record onto a Document, auto-filling only what we trust."""
    document.summary = understanding.summary or None
    document.key_facts = understanding.key_facts or None
    document.topic_tags = understanding.tags or None
    document.detected_doc_type = understanding.doc_type
    document.detected_vendors = understanding.vendors or None
    document.detected_products = understanding.products or None
    document.detected_version_label = understanding.version_label
    document.understanding_confidence = understanding.confidence
    document.understanding_source = understanding.origin
    document.understood_at = datetime.now(timezone.utc)

    if not understanding.is_confident:
        return

    # Enrichment only fills blanks. A person's edit always wins.
    if not document.vendor and understanding.vendors:
        document.vendor = understanding.vendors[0][:255]
    if not document.products_referenced and understanding.products:
        document.products_referenced = understanding.products
    if document.valid_until is None and understanding.valid_until is not None:
        document.valid_until = understanding.valid_until


# -- small helpers ----------------------------------------------------------


def _as_text(value) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value.strip()
    return str(value).strip()


def _as_list(value, *, limit: int) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        items = [part.strip() for part in value.split(",")]
    elif isinstance(value, (list, tuple)):
        items = [_as_text(part) for part in value]
    else:
        return []
    return _unique(items)[:limit]


def _as_facts(value) -> list[dict]:
    if not isinstance(value, (list, tuple)):
        return []
    facts: list[dict] = []
    for item in value:
        if isinstance(item, dict):
            label = _as_text(item.get("label"))[:120]
            fact = _as_text(item.get("value"))[:400]
        elif isinstance(item, str) and ":" in item:
            label, _, fact = item.partition(":")
            label, fact = label.strip()[:120], fact.strip()[:400]
        else:
            continue
        if label and fact:
            facts.append({"label": label, "value": fact})
        if len(facts) == 8:
            break
    return facts


def _as_date(value) -> date | None:
    text = _as_text(value)
    if not text:
        return None
    match = _ISO_DATE.search(text)
    if not match:
        return None
    try:
        return date(int(match.group(1)), int(match.group(2)), int(match.group(3)))
    except ValueError:
        return None


def _as_confidence(value) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return 0.0
    return max(0.0, min(1.0, number))


def _unique(items) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for item in items:
        cleaned = _as_text(item).strip(" .;,")
        if not cleaned:
            continue
        key = cleaned.lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(cleaned)
    return out


def _lead_summary(text: str, *, max_chars: int = 900) -> str:
    body = " ".join(text.split())
    if not body:
        return ""
    sentences = _SENTENCE_SPLIT.split(body)
    picked: list[str] = []
    total = 0
    for sentence in sentences:
        if not sentence:
            continue
        picked.append(sentence)
        total += len(sentence) + 1
        if len(picked) >= 6 or total >= max_chars:
            break
    return " ".join(picked)[:max_chars].strip()


def _label_facts(text: str) -> list[dict]:
    facts: list[dict] = []
    seen: set[str] = set()
    for line in text.splitlines():
        match = _LABEL_LINE.match(line)
        if not match:
            continue
        label = match.group(1).strip()[:120]
        value = match.group(2).strip()[:400]
        key = label.lower()
        if key in seen or not value:
            continue
        seen.add(key)
        facts.append({"label": label, "value": value})
        if len(facts) == 8:
            break
    return facts
