"""Decide what a file actually is from its bytes, not from its name.

Project_Plan.md Phase 1: "File type and size validated by content sniffing, not
extension." Deliberately dependency-free: `libmagic` is a native library that is
awkward on Render, and the signatures we care about are a dozen byte patterns.
"""

from __future__ import annotations

import io
import zipfile
from dataclasses import dataclass
from pathlib import Path

# Canonical types the pipeline can extract. Everything else is refused at the door.
SUPPORTED_TYPES: frozenset[str] = frozenset({"pdf", "docx", "pptx", "xlsx", "txt", "md", "html"})

# Types that carry structural citation anchors (page, slide, sheet+cell).
ANCHORED_TYPES: frozenset[str] = frozenset({"pdf", "pptx", "xlsx"})

_EXTENSION_ALIASES = {
    "text": "txt",
    "markdown": "md",
    "mdown": "md",
    "htm": "html",
    "xhtml": "html",
}

_OOXML_MARKERS = (
    ("word/", "docx"),
    ("ppt/", "pptx"),
    ("xl/", "xlsx"),
)

_HTML_HINTS = (b"<!doctype html", b"<html", b"<head", b"<body")


@dataclass(frozen=True)
class SniffResult:
    file_type: str | None
    container: str | None  # "zip" for OOXML, None otherwise
    detail: str

    @property
    def is_known(self) -> bool:
        return self.file_type is not None


def normalize_extension(filename: str) -> str:
    suffix = Path(filename).suffix.lower().lstrip(".")
    return _EXTENSION_ALIASES.get(suffix, suffix)


def sniff(data: bytes) -> SniffResult:
    """Best-effort content identification of an in-memory upload."""
    if not data:
        return SniffResult(None, None, "empty file")

    head = data[:4096]

    if head.startswith(b"%PDF-"):
        return SniffResult("pdf", None, "PDF header")

    if head[:2] == b"PK":
        return _sniff_zip(data)

    # Reject the obvious executables and archives explicitly, so the error message
    # is useful instead of "could not decode text".
    for magic, label in (
        (b"\x7fELF", "ELF executable"),
        (b"MZ", "Windows executable"),
        (b"\xca\xfe\xba\xbe", "Mach-O / Java class"),
        (b"\x1f\x8b", "gzip archive"),
        (b"Rar!", "RAR archive"),
        (b"\xfd7zXZ", "xz archive"),
        (b"7z\xbc\xaf\x27\x1c", "7z archive"),
        (b"{\\rtf", "RTF document"),
        (b"\xd0\xcf\x11\xe0", "legacy Office (OLE2) document"),
    ):
        if head.startswith(magic):
            return SniffResult(None, None, f"{label} is not an accepted format")

    text = _try_decode(head)
    if text is None:
        return SniffResult(None, None, "binary content with no recognised signature")

    lowered = text.lstrip().lower()
    if any(lowered.startswith(hint) or hint in lowered[:1024] for hint in _HTML_HINTS_STR):
        return SniffResult("html", None, "HTML markup")
    return SniffResult("txt", None, "decodable text")


_HTML_HINTS_STR = tuple(h.decode() for h in _HTML_HINTS)


def _sniff_zip(data: bytes) -> SniffResult:
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            names = archive.namelist()
    except zipfile.BadZipFile:
        return SniffResult(None, "zip", "truncated or corrupt ZIP container")
    for marker, file_type in _OOXML_MARKERS:
        if any(name.startswith(marker) for name in names):
            return SniffResult(file_type, "zip", f"OOXML package containing {marker}")
    return SniffResult(None, "zip", "ZIP archive that is not a supported OOXML package")


def _try_decode(data: bytes) -> str | None:
    if b"\x00" in data:
        return None
    for encoding in ("utf-8", "utf-16"):
        try:
            return data.decode(encoding)
        except UnicodeDecodeError:
            continue
    try:
        decoded = data.decode("latin-1")
    except UnicodeDecodeError:
        return None
    # latin-1 never fails, so require that the bytes look like text.
    printable = sum(1 for ch in decoded if ch.isprintable() or ch in "\r\n\t")
    return decoded if printable / max(len(decoded), 1) > 0.85 else None


@dataclass(frozen=True)
class TypeDecision:
    file_type: str
    sniffed: SniffResult
    declared_extension: str
    declared_mime: str | None
    extension_mismatch: bool

    def as_dict(self) -> dict:
        return {
            "file_type": self.file_type,
            "declared_extension": self.declared_extension or None,
            "declared_mime": self.declared_mime,
            "sniffed": self.sniffed.detail,
            "extension_mismatch": self.extension_mismatch,
        }


def decide_file_type(filename: str, data: bytes, declared_mime: str | None = None) -> TypeDecision:
    """Content wins. The declared extension is recorded, never trusted.

    Raises `UnsupportedFileType` with a message a human can act on.
    """
    from app.core.errors import UnsupportedFileType

    extension = normalize_extension(filename)
    result = sniff(data)

    if result.file_type is None:
        raise UnsupportedFileType(
            f"unsupported or unsafe file: {result.detail}. "
            f"Accepted: {', '.join(sorted(SUPPORTED_TYPES))}"
        )

    file_type = result.file_type
    # `md` and `txt` are byte-identical; the extension is the only signal, and
    # trusting it here is harmless because both take the same parser.
    if file_type == "txt" and extension == "md":
        file_type = "md"

    mismatch = bool(extension) and extension != file_type and not (
        {extension, file_type} <= {"txt", "md"}
    )
    return TypeDecision(
        file_type=file_type,
        sniffed=result,
        declared_extension=extension,
        declared_mime=declared_mime,
        extension_mismatch=mismatch,
    )
