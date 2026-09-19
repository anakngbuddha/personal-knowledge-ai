"""Pre-parse safety limits.

Project_Plan.md asks for "parsing in a resource-limited sandbox with timeouts" plus
"XXE and zip-bomb protections for archives, OOXML, and HTML".

Honest scope note, because the difference matters: a real sandbox (seccomp, a
separate container, cgroup memory caps) belongs to the deployment, not to this
process, and claiming one in application code would be a lie. What is implemented
here is the part application code *can* enforce, and it is the part that actually
stops the attacks in question:

* a wall-clock deadline that extraction loops check, so no single file can pin a
  worker forever
* hard caps on archive entry count, uncompressed size, and compression ratio, which
  is what kills a zip bomb before any XML parser sees it
* rejection of any OOXML part that declares a DTD or an entity, which is what kills
  XXE and billion-laughs regardless of what the underlying parser does by default
* path-traversal rejection on archive member names
* a cap on total extracted characters

The residual gap (true process isolation) is recorded in docs/PHASE1-2.md rather
than papered over.
"""

from __future__ import annotations

import io
import re
import time
import zipfile
from dataclasses import dataclass, field

from app.core.config import settings
from app.core.errors import ExtractionTimeout, UnsafeFile

_DOCTYPE_RE = re.compile(rb"<!\s*(DOCTYPE|ENTITY)", re.IGNORECASE)
_XML_PART_SUFFIXES = (".xml", ".rels", ".xhtml", ".html", ".svg")


@dataclass
class ParseLimits:
    timeout_seconds: float = field(default_factory=lambda: settings.parse_timeout_seconds)
    max_archive_entries: int = field(default_factory=lambda: settings.max_archive_entries)
    max_uncompressed_bytes: int = field(default_factory=lambda: settings.max_uncompressed_bytes)
    max_compression_ratio: float = field(default_factory=lambda: settings.max_compression_ratio)
    max_pdf_pages: int = field(default_factory=lambda: settings.max_pdf_pages)
    max_extracted_chars: int = field(default_factory=lambda: settings.max_extracted_chars)

    def deadline(self) -> Deadline:
        return Deadline(self.timeout_seconds)


class Deadline:
    """Cooperative wall-clock budget. Extraction loops call `check()` per page."""

    def __init__(self, seconds: float, clock=time.monotonic) -> None:
        self._clock = clock
        self._seconds = seconds
        self._start = clock()

    @property
    def elapsed(self) -> float:
        return self._clock() - self._start

    @property
    def remaining(self) -> float:
        return self._seconds - self.elapsed

    @property
    def expired(self) -> bool:
        return self.remaining <= 0

    def check(self, what: str = "parsing") -> None:
        if self.expired:
            raise ExtractionTimeout(
                f"{what} exceeded its {self._seconds:g}s budget "
                f"(elapsed {self.elapsed:.1f}s)"
            )


@dataclass
class ArchiveReport:
    entries: int
    compressed_bytes: int
    uncompressed_bytes: int
    ratio: float
    declares_dtd: bool

    def as_dict(self) -> dict:
        return {
            "entries": self.entries,
            "compressed_bytes": self.compressed_bytes,
            "uncompressed_bytes": self.uncompressed_bytes,
            "ratio": round(self.ratio, 2),
            "declares_dtd": self.declares_dtd,
        }


def inspect_ooxml(data: bytes, limits: ParseLimits | None = None) -> ArchiveReport:
    """Validate an OOXML package before any Office parser touches it.

    Raises `UnsafeFile` on anything that looks like a bomb, a traversal attempt, or
    an XML entity trick.
    """
    limits = limits or ParseLimits()
    try:
        archive = zipfile.ZipFile(io.BytesIO(data))
    except zipfile.BadZipFile as exc:
        raise UnsafeFile(f"not a readable OOXML package: {exc}") from exc

    with archive:
        infos = archive.infolist()
        if len(infos) > limits.max_archive_entries:
            raise UnsafeFile(
                f"archive has {len(infos)} entries, limit is {limits.max_archive_entries}"
            )

        uncompressed = 0
        compressed = 0
        for info in infos:
            _reject_unsafe_name(info.filename)
            if info.file_size < 0:
                raise UnsafeFile(f"archive entry {info.filename!r} reports a negative size")
            uncompressed += info.file_size
            compressed += max(info.compress_size, 0)
            if uncompressed > limits.max_uncompressed_bytes:
                raise UnsafeFile(
                    f"archive expands to more than {limits.max_uncompressed_bytes} bytes "
                    "(possible zip bomb)"
                )

        ratio = uncompressed / compressed if compressed else 0.0
        # A tiny package can legitimately have a wild ratio, so only judge ratio
        # once the expansion is big enough to matter.
        if uncompressed > 8 * 1024 * 1024 and ratio > limits.max_compression_ratio:
            raise UnsafeFile(
                f"archive compression ratio {ratio:.0f}x exceeds the "
                f"{limits.max_compression_ratio:.0f}x limit (possible zip bomb)"
            )

        declares_dtd = False
        for info in infos:
            if not info.filename.lower().endswith(_XML_PART_SUFFIXES):
                continue
            # Only the head of each part is needed: a DTD must appear in the prolog.
            with archive.open(info) as handle:
                prolog = handle.read(8192)
            if _DOCTYPE_RE.search(prolog):
                declares_dtd = True
                raise UnsafeFile(
                    f"XML part {info.filename!r} declares a DOCTYPE or ENTITY; "
                    "refusing to parse (XXE / entity expansion)"
                )

    return ArchiveReport(
        entries=len(infos),
        compressed_bytes=compressed,
        uncompressed_bytes=uncompressed,
        ratio=ratio,
        declares_dtd=declares_dtd,
    )


def _reject_unsafe_name(name: str) -> None:
    normalized = name.replace("\\", "/")
    if normalized.startswith("/") or normalized.startswith("../") or "/../" in normalized:
        raise UnsafeFile(f"archive entry {name!r} escapes the package root")
    if ":" in normalized.split("/")[0] and len(normalized.split("/")[0]) == 2:
        raise UnsafeFile(f"archive entry {name!r} uses an absolute drive path")


def check_html_safety(data: bytes) -> None:
    """HTML is parsed with the stdlib tolerant parser, which never resolves external
    entities or loads a DTD. The one thing still worth refusing outright is a
    declared ENTITY, because in an HTML collateral document it is a reliable signal
    of an XXE or entity-expansion attempt rather than real content."""
    head = data[:8192].upper()
    if b"<!ENTITY" in head.replace(b"<! ENTITY", b"<!ENTITY"):
        raise UnsafeFile("HTML declares an ENTITY; refusing to parse")


def guard_extracted_size(total_chars: int, limits: ParseLimits | None = None) -> None:
    limits = limits or ParseLimits()
    if total_chars > limits.max_extracted_chars:
        raise UnsafeFile(
            f"extracted {total_chars} characters, limit is {limits.max_extracted_chars}"
        )
