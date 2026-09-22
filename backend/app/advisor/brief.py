"""4.1 Customer brief: remember what the customer actually asked for.

A salesperson pastes a chunk of a customer's email, or uploads their requirements, and
then asks questions against it for the rest of the call. Until now that text was read
once by :func:`extract_discovery_constraints`, which could find a budget and a seat count
and not much else, and nothing survived the turn.

This module reads the same text properly:

* one model call turns it into a structured brief (industry, size, rooms, platforms,
  cloud needs, budget, constraints, timeline, must-haves, nice-to-haves, exclusions);
* a deterministic reader fills the same fields when the model is unavailable, returns
  prose, or is switched off, so the offline suite exercises a real path;
* the numbers the old regex was good at (budget, seats) are re-checked against the text
  and win over the model, because a hallucinated seat count is worse than none.

The brief is stored as a Note so it is searchable, backlinkable, and retrievable like
any other note, and so the user can edit it in the Notes screen.

Containment: requirement text is customer-supplied and therefore untrusted. It reaches
the model only through ``wrap_untrusted()`` under ``SYSTEM_CONTRACT``, exactly like a
document. A requirements sheet cannot instruct the advisor.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field

from app.core.config import settings
from app.core.logging import get_logger
from app.documents.injection import SYSTEM_CONTRACT, neutralize_fences, wrap_untrusted

logger = get_logger(__name__)

BRIEF_PROMPT_VERSION = "1.0.0"

BRIEF_SYSTEM_PROMPT = f"""You turn one customer's requirements into a short structured brief
for a salesperson.

{SYSTEM_CONTRACT}

Return exactly one JSON object and nothing else. No prose before it, no prose after it.

Keys:
  customer        the customer or account name if the text names one, else null
  industry        the customer's industry if stated, else null
  size            headcount or company size if stated, else null
  users           total number of people or seats to equip, as an integer, else null
  rooms           list of objects with "room_type" (huddle room, meeting room, boardroom,
                  contact center, home office, auditorium, training room, other),
                  "count" (integer or null) and "platform" (Microsoft Teams, Zoom, Webex,
                  Google Meet or null)
  platforms       meeting or collaboration platforms named in the text
  cloud_needs     list of short phrases for any cloud, backup, DR or network need stated
  budget          the budget as written in the text, else null
  timeline        the deadline or timeline as written, else null
  constraints     list of short phrases: rules the solution must respect
  must_haves      list of short phrases the customer requires
  nice_to_haves   list of short phrases the customer would like
  exclusions      list of vendors, products or approaches the customer ruled out
  confidence      0.0 to 1.0, how sure you are this brief reflects the text

Rules:
  * Only record what the text states. An empty list is a correct answer.
  * Never invent a budget, a seat count, a platform, a vendor or a date.
  * Copy numbers exactly as written. Do not convert, round or total them.
  * Report confidence below 0.5 when the text is vague or mostly prose.
"""

BRIEF_REQUEST = "Turn the requirements above into the JSON brief. Reply with the JSON object only."

_ROOM_TYPES: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("contact center", ("contact center", "contact centre", "call center", "call centre")),
    ("huddle room", ("huddle room", "huddle space", "focus room")),
    ("boardroom", ("boardroom", "board room", "executive room")),
    ("training room", ("training room", "classroom")),
    ("auditorium", ("auditorium", "town hall space", "lecture hall")),
    ("home office", ("home office", "remote worker", "work from home", "hybrid worker")),
    ("meeting room", ("meeting room", "conference room", "medium room", "large room")),
)

_PLATFORMS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("Microsoft Teams", ("microsoft teams", "ms teams", "teams rooms", "teams room", "teams")),
    ("Zoom", ("zoom rooms", "zoom room", "zoom")),
    ("Webex", ("webex",)),
    ("Google Meet", ("google meet", "google workspace")),
)

_CLOUD_NEEDS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("backup", ("backup", "back-up")),
    ("disaster recovery", ("disaster recovery", "dr site", " dr ", "business continuity")),
    ("storage", ("object storage", "storage")),
    ("compute", ("virtual machine", "compute", "ecs ")),
    ("network", ("sd-wan", "bandwidth", "networking", "vpn")),
    ("security", ("firewall", "waf", "security")),
)

#: The two numbers the deterministic reader is genuinely good at, kept as validation.
_BUDGET = re.compile(
    r"(?:budget|cap(?:ped)?(?: at)?|not to exceed|up to)\s*[:=]?\s*"
    r"([$\u20ac\u00a3\u20b1]?\s*[\d][\d,.]*(?:\s*[kKmM]\b)?(?:\s*(?:USD|PHP|EUR|GBP))?)",
    re.IGNORECASE,
)
_SEATS = re.compile(
    r"([\d][\d,]*)\s*[- ]?\s*(?:seat|seats|users|agents|employees|people|staff)\b",
    re.IGNORECASE,
)
_TIMELINE = re.compile(
    r"\b(?:by|before|within|deadline(?: is)?|go[- ]live(?: is)?|target(?: date)?(?: is)?)\s+"
    r"([A-Z][a-z]+ \d{1,2}(?:,? \d{4})?|\d{4}-\d{2}-\d{2}|Q[1-4](?: \d{4})?|\d+\s+(?:days|weeks|months))",
    re.IGNORECASE,
)
_EXCLUSION = re.compile(
    # A few words at most, and never across a sentence boundary: "No Cisco please." is
    # an exclusion of Cisco, not of the rest of the paragraph.
    r"\b(?:no|not|avoid|exclude|excluding|rule out|ruled out|without|cannot use|can't use)\s+"
    r"([A-Za-z0-9+-]+(?:\s+[A-Za-z0-9+-]+){0,3})",
    re.IGNORECASE,
)

#: Words that ride along after "no <vendor>" and are not part of what was ruled out.
_EXCLUSION_FILLER = {
    "please", "thanks", "thank", "for", "at", "in", "on", "to", "and", "or", "we", "us",
    "this", "that", "the", "a", "an", "is", "are", "be", "been", "it", "if", "as", "by",
    "need", "needs", "needed", "want", "wants", "required", "allowed", "possible",
    "interested", "keen", "looking", "able", "willing", "going", "using", "considering",
    "have", "has", "had", "do", "does", "did", "will", "would", "can", "could",
}
_MUST = re.compile(
    r"\b(?:must have|must be|must include|mandatory|non[- ]negotiable|required)\b\s*[:-]?\s*([^.;\n]{4,160})",
    re.IGNORECASE,
)
_NICE = re.compile(
    r"\b(?:nice to have|would like|prefer(?:ably)?|ideally|bonus)\b\s*[:-]?\s*([^.;\n]{4,160})",
    re.IGNORECASE,
)
_INDUSTRY = re.compile(
    r"\b(banking|financial services|insurance|healthcare|hospital|education|university|"
    r"government|public sector|retail|manufacturing|logistics|bpo|telecom|energy|mining|"
    r"hospitality|legal|construction)\b",
    re.IGNORECASE,
)

#: A word that is never a room type, however many of them the text counts.
_NOT_A_ROOM = {
    "year", "years", "month", "months", "week", "weeks", "day", "days", "hour", "hours",
    "seat", "seats", "user", "users", "agent", "agents", "employee", "employees",
    "people", "staff", "site", "sites", "office", "offices", "branch", "branches",
    "floor", "floors", "license", "licenses", "licence", "licences", "unit", "units",
}


@dataclass
class RoomRequirement:
    room_type: str
    count: int | None = None
    platform: str | None = None
    #: People in the space, when the text counted seats or agents instead of rooms.
    seats: int | None = None

    def as_dict(self) -> dict:
        return {
            "room_type": self.room_type,
            "count": self.count,
            "platform": self.platform,
            "seats": self.seats,
        }

    def as_phrase(self) -> str:
        if self.seats and not self.count:
            head = f"{self.seats}-seat {self.room_type}"
        elif self.count:
            head = f"{self.count} {self.room_type}"
            if self.count != 1 and not self.room_type.endswith("s"):
                head += "s"
        else:
            head = self.room_type
        return f"{head} on {self.platform}" if self.platform else head


@dataclass
class CustomerBrief:
    """What the customer asked for. Every field is optional by design."""

    customer: str | None = None
    industry: str | None = None
    size: str | None = None
    users: int | None = None
    rooms: list[RoomRequirement] = field(default_factory=list)
    platforms: list[str] = field(default_factory=list)
    cloud_needs: list[str] = field(default_factory=list)
    budget: str | None = None
    timeline: str | None = None
    constraints: list[str] = field(default_factory=list)
    must_haves: list[str] = field(default_factory=list)
    nice_to_haves: list[str] = field(default_factory=list)
    exclusions: list[str] = field(default_factory=list)
    confidence: float = 0.0
    origin: str = "heuristic"  # llm | heuristic
    prompt_version: str = BRIEF_PROMPT_VERSION
    source_excerpt: str = ""

    @property
    def is_empty(self) -> bool:
        return not any(
            [
                self.customer, self.industry, self.size, self.users, self.rooms,
                self.platforms, self.cloud_needs, self.budget, self.timeline,
                self.constraints, self.must_haves, self.nice_to_haves, self.exclusions,
            ]
        )

    def requirement_phrases(self) -> list[str]:
        """Every requirement as one short line, for matching and for restating."""
        phrases = [room.as_phrase() for room in self.rooms]
        phrases += list(self.cloud_needs)
        phrases += list(self.must_haves)
        phrases += list(self.nice_to_haves)
        out: list[str] = []
        seen: set[str] = set()
        for phrase in phrases:
            cleaned = " ".join(str(phrase).split())
            key = cleaned.lower()
            if not cleaned or key in seen:
                continue
            seen.add(key)
            out.append(cleaned)
        return out

    def as_dict(self) -> dict:
        return {
            "customer": self.customer,
            "industry": self.industry,
            "size": self.size,
            "users": self.users,
            "rooms": [room.as_dict() for room in self.rooms],
            "platforms": list(self.platforms),
            "cloud_needs": list(self.cloud_needs),
            "budget": self.budget,
            "timeline": self.timeline,
            "constraints": list(self.constraints),
            "must_haves": list(self.must_haves),
            "nice_to_haves": list(self.nice_to_haves),
            "exclusions": list(self.exclusions),
            "confidence": self.confidence,
            "origin": self.origin,
            "prompt_version": self.prompt_version,
        }

    def as_markdown(self) -> str:
        """The note body. Plain words only: this is read by a salesperson."""
        lines = ["# Customer brief", ""]
        if self.customer:
            lines.append(f"**Customer:** {self.customer}")
        if self.industry:
            lines.append(f"**Industry:** {self.industry}")
        if self.size:
            lines.append(f"**Size:** {self.size}")
        if self.users:
            lines.append(f"**People to equip:** {self.users}")
        if self.budget:
            lines.append(f"**Budget:** {self.budget}")
        if self.timeline:
            lines.append(f"**Timeline:** {self.timeline}")
        if self.platforms:
            lines.append(f"**Platforms:** {', '.join(self.platforms)}")
        lines.append("")

        def block(title: str, items: list[str]) -> None:
            if not items:
                return
            lines.append(f"## {title}")
            lines.extend(f"- {item}" for item in items)
            lines.append("")

        block("Rooms and spaces", [room.as_phrase() for room in self.rooms])
        block("Cloud and network needs", self.cloud_needs)
        block("Must have", self.must_haves)
        block("Nice to have", self.nice_to_haves)
        block("Constraints", self.constraints)
        block("Ruled out", self.exclusions)
        if self.source_excerpt:
            lines += [
                "## What the customer sent",
                "",
                "> " + self.source_excerpt.replace("\n", "\n> "),
                "",
            ]
        return "\n".join(lines).strip() + "\n"

    def note_title(self) -> str:
        who = self.customer or self.industry or "customer"
        return f"Customer brief: {who}"[:512]


def extract_customer_brief(text: str, *, provider=None) -> CustomerBrief:
    """Read requirement text into a brief. Always returns something; never raises."""
    cleaned = neutralize_fences(text or "").strip()
    if not cleaned:
        return CustomerBrief(confidence=0.0, origin="heuristic")

    excerpt = cleaned[: max(500, settings.advisor_brief_max_chars)]
    brief: CustomerBrief | None = None

    if settings.advisor_brief_extraction_enabled:
        try:
            payload = _parse_json_object(_ask_model(excerpt, provider=provider))
            if payload is not None:
                brief = _from_payload(payload)
            if brief is None:
                logger.info(
                    "customer brief: model reply was not usable JSON; using the offline reader"
                )
        except Exception:  # noqa: BLE001 - a brief is never worth failing a question over
            logger.warning("customer brief: model call failed", exc_info=True)

    if brief is None:
        brief = heuristic_brief(excerpt)

    # The old regex was reliable about money and seats. Let it have the last word.
    validate_numbers(brief, excerpt)
    brief.source_excerpt = excerpt[:1200]
    return brief


def _ask_model(excerpt: str, *, provider=None) -> str:
    if provider is None:
        from app.llm.factory import get_llm_provider

        provider = get_llm_provider()

    context_chunks = [
        {
            "index": 1,
            "fenced_text": wrap_untrusted(excerpt, source="customer requirements"),
            "citation": "customer requirements",
            "metadata": {"document_title": "customer requirements"},
        }
    ]
    answer = provider.generate_grounded_answer(
        BRIEF_REQUEST,
        context_chunks,
        system_prompt=BRIEF_SYSTEM_PROMPT,
    )
    return answer.text or ""


def validate_numbers(brief: CustomerBrief, text: str) -> CustomerBrief:
    """Re-check the money and the seat count against the text itself."""
    budget = _BUDGET.search(text)
    if budget:
        brief.budget = " ".join(budget.group(1).split()).strip(" .,;:")
    elif brief.budget and _digits(brief.budget) and _digits(brief.budget) not in _digits(text):
        # A budget with digits the text never contained is a hallucination.
        brief.budget = None

    if brief.users is None:
        seats = [_int(match) for match in _SEATS.findall(text)]
        seats = [value for value in seats if value]
        if seats:
            brief.users = max(seats)
    return brief


def heuristic_brief(text: str) -> CustomerBrief:
    """Deterministic offline reader. Same fields, honest low confidence."""
    lowered = text.lower()

    platforms = [name for name, hints in _PLATFORMS if any(hint in lowered for hint in hints)]
    cloud_needs = [name for name, hints in _CLOUD_NEEDS if any(hint in lowered for hint in hints)]

    rooms: list[RoomRequirement] = []
    for canonical, hints in _ROOM_TYPES:
        hit = next((hint for hint in hints if hint in lowered), None)
        if hit is None:
            continue
        counted, is_seats = _count_before(lowered, hints)
        rooms.append(
            RoomRequirement(
                room_type=canonical,
                count=None if is_seats else counted,
                seats=counted if is_seats else None,
                # Only a platform written near the room is attributed to it. A platform
                # named elsewhere in the email is recorded on the brief, not guessed onto
                # every space.
                platform=_platform_near(lowered, hit),
            )
        )

    industry = _INDUSTRY.search(text)
    timeline = _TIMELINE.search(text)

    return CustomerBrief(
        industry=industry.group(1).lower() if industry else None,
        rooms=rooms,
        platforms=platforms,
        cloud_needs=cloud_needs,
        timeline=" ".join(timeline.group(1).split()) if timeline else None,
        must_haves=_phrases(_MUST.findall(text), limit=8),
        nice_to_haves=_phrases(_NICE.findall(text), limit=6),
        exclusions=_phrases(_trim_filler(_EXCLUSION.findall(text)), limit=6),
        # Deliberately below the auto-trust bar: a regex reading is a starting point.
        confidence=0.35,
        origin="heuristic",
    )


def save_brief_as_note(
    db,
    *,
    org_id,
    workspace_id,
    brief: CustomerBrief,
    created_by=None,
    account: str | None = None,
    notebook_id=None,
):
    """Store the brief as a note, so it is searchable and editable like any other."""
    from app.notes import service as notes

    body = brief.as_markdown()
    if account:
        body = f"Account: [[account:{account}]]\n\n{body}"
    return notes.create_note(
        db,
        org_id=org_id,
        workspace_id=workspace_id,
        title=brief.note_title(),
        body=body,
        created_by=created_by,
        notebook_id=notebook_id,
    )


# -- small helpers ----------------------------------------------------------


def _from_payload(payload: dict) -> CustomerBrief | None:
    brief = CustomerBrief(
        customer=_as_text(payload.get("customer"))[:255] or None,
        industry=_as_text(payload.get("industry"))[:120] or None,
        size=_as_text(payload.get("size"))[:120] or None,
        users=_as_int(payload.get("users")),
        rooms=_as_rooms(payload.get("rooms")),
        platforms=_as_list(payload.get("platforms"), limit=6),
        cloud_needs=_as_list(payload.get("cloud_needs"), limit=10),
        budget=_as_text(payload.get("budget"))[:120] or None,
        timeline=_as_text(payload.get("timeline"))[:120] or None,
        constraints=_as_list(payload.get("constraints"), limit=10),
        must_haves=_as_list(payload.get("must_haves"), limit=12),
        nice_to_haves=_as_list(payload.get("nice_to_haves"), limit=10),
        exclusions=_as_list(payload.get("exclusions"), limit=10),
        confidence=_as_confidence(payload.get("confidence")),
        origin="llm",
    )
    return None if brief.is_empty else brief


def _as_rooms(value) -> list[RoomRequirement]:
    if not isinstance(value, (list, tuple)):
        return []
    rooms: list[RoomRequirement] = []
    for item in value:
        if isinstance(item, dict):
            room_type = _as_text(item.get("room_type")).lower()[:60]
            count = _as_int(item.get("count"))
            platform = _as_text(item.get("platform"))[:60] or None
            seats = _as_int(item.get("seats"))
        elif isinstance(item, str):
            room_type, count, platform, seats = _as_text(item).lower()[:60], None, None, None
        else:
            continue
        if not room_type:
            continue
        rooms.append(
            RoomRequirement(room_type=room_type, count=count, platform=platform, seats=seats)
        )
        if len(rooms) == 12:
            break
    return rooms


def _parse_json_object(raw: str) -> dict | None:
    """Pull the first JSON object out of a reply, fenced or bare."""
    if not raw:
        return None
    text = raw.strip()
    if text.startswith("```"):
        text = re.sub(r"^```[a-zA-Z]*\s*", "", text)
        text = re.sub(r"```\s*$", "", text).strip()
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end <= start:
        return None
    try:
        parsed = json.loads(text[start : end + 1])
    except (ValueError, TypeError):
        return None
    return parsed if isinstance(parsed, dict) else None


def _count_before(lowered: str, hints: tuple[str, ...]) -> tuple[int | None, bool]:
    """The number written just before a room phrase, and whether it counts people.

    "12 huddle rooms" is twelve rooms. "a 40-seat contact center" is one room with forty
    people in it, and reading that as forty contact centres would put forty times too
    much in the recommendation.
    """
    for hint in hints:
        for match in re.finditer(
            rf"([\d][\d,]*)\s*(?:x\s*)?((?:[a-z-]+\s+){{0,2}}){re.escape(hint)}", lowered
        ):
            value = _int(match.group(1))
            if not value:
                continue
            between = match.group(2) or ""
            is_seats = bool(re.search(r"seat|agent|user|person|people|position", between))
            return value, is_seats
    return None, False


def _platform_near(lowered: str, hint: str, window: int = 90) -> str | None:
    position = lowered.find(hint)
    if position == -1:
        return None
    around = lowered[max(0, position - window) : position + len(hint) + window]
    for name, hints in _PLATFORMS:
        if any(candidate in around for candidate in hints):
            return name
    return None


def _trim_filler(items) -> list[str]:
    """Keep only the named thing: "Cisco please. We need" -> "Cisco"."""
    out: list[str] = []
    for item in items:
        # Stop at the first sentence break: "Zoom. Avoid Poly" is one exclusion here,
        # and "Poly" is found again by the next match.
        words = re.split(r"[.,;:!?]", str(item))[0].split()
        kept: list[str] = []
        for word in words:
            filler = word.lower() in _EXCLUSION_FILLER
            if filler and not kept:
                continue  # "not interested in Huawei" rules out Huawei, not interest
            if filler:
                break
            kept.append(word)
        if kept:
            out.append(" ".join(kept))
    return out


def _phrases(items, *, limit: int) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for item in items:
        cleaned = " ".join(str(item).split()).strip(" .,;:-")
        if len(cleaned) < 3 or cleaned.lower() in _NOT_A_ROOM:
            continue
        key = cleaned.lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(cleaned[:160])
        if len(out) == limit:
            break
    return out


def _as_text(value) -> str:
    if value is None:
        return ""
    return value.strip() if isinstance(value, str) else str(value).strip()


def _as_list(value, *, limit: int) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        items = [part.strip() for part in value.split(",")]
    elif isinstance(value, (list, tuple)):
        items = [_as_text(part) for part in value]
    else:
        return []
    return _phrases(items, limit=limit)


def _as_int(value) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value if value > 0 else None
    return _int(_as_text(value))


def _int(value: str) -> int | None:
    digits = re.sub(r"[^\d]", "", str(value or ""))
    if not digits:
        return None
    try:
        number = int(digits)
    except ValueError:
        return None
    return number if 0 < number < 10_000_000 else None


def _digits(value: str) -> str:
    return re.sub(r"[^\d]", "", str(value or ""))


def _as_confidence(value) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return 0.0
    return max(0.0, min(1.0, number))
