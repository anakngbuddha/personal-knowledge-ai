"""Parse [[wikilinks]] that bind SE notes to products, accounts, and other notes.

Supported forms:
  [[product:firewall-plus]]
  [[account:acme-corp]]
  [[note:sizing-acme]]
  [[firewall-plus]]                  # unprefixed; resolved later
  [[product:firewall-plus|Firewall]] # alias after a pipe
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from app.db.models import NoteLinkKind

WIKILINK_RE = re.compile(r"\[\[([^\]]+)\]\]")
KIND_PREFIXES = {
    "product": NoteLinkKind.PRODUCT,
    "account": NoteLinkKind.ACCOUNT,
    "note": NoteLinkKind.NOTE,
}


@dataclass(frozen=True)
class ParsedWikilink:
    raw: str
    kind: str
    target_ref: str
    display_text: str | None
    prefixed: bool


def _normalize_ref(value: str) -> str:
    return re.sub(r"[\s_]+", "-", value.strip().lower()).strip("-")


def parse_wikilink_inner(inner: str) -> ParsedWikilink:
    raw = inner.strip()
    display: str | None = None
    target = raw
    if "|" in raw:
        target, alias = raw.split("|", 1)
        target = target.strip()
        display = alias.strip() or None

    kind = NoteLinkKind.NOTE
    prefixed = False
    if ":" in target:
        prefix, rest = target.split(":", 1)
        mapped = KIND_PREFIXES.get(prefix.strip().lower())
        if mapped and rest.strip():
            kind = mapped
            target = rest.strip()
            prefixed = True

    ref = _normalize_ref(target)
    return ParsedWikilink(
        raw=inner.strip(),
        kind=kind,
        target_ref=ref,
        display_text=display,
        prefixed=prefixed,
    )


def extract_wikilinks(markdown: str) -> list[ParsedWikilink]:
    """Return unique wikilinks in document order."""
    seen: set[tuple[str, str]] = set()
    out: list[ParsedWikilink] = []
    for match in WIKILINK_RE.finditer(markdown or ""):
        parsed = parse_wikilink_inner(match.group(1))
        if not parsed.target_ref:
            continue
        key = (parsed.kind, parsed.target_ref)
        if key in seen:
            continue
        seen.add(key)
        out.append(parsed)
    return out
