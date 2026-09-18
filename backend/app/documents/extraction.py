"""Text extraction that preserves as much structure as the parser can give us.

Page boundaries and headings are what make citations trustworthy, so they are captured
during extraction rather than reconstructed after chunking.
"""

from dataclasses import dataclass, field
from pathlib import Path

from app.core.errors import ExtractionError, UnsupportedFileType

SUPPORTED_TYPES = {"pdf", "txt", "docx"}


@dataclass
class Block:
    """A structural unit of source text (a page, paragraph, or section body)."""

    text: str
    page_number: int | None = None
    section_title: str | None = None


@dataclass
class ExtractionResult:
    blocks: list[Block] = field(default_factory=list)
    page_count: int | None = None
    metadata: dict = field(default_factory=dict)


def detect_file_type(filename: str) -> str:
    suffix = Path(filename).suffix.lower().lstrip(".")
    if suffix == "text":
        suffix = "txt"
    if suffix not in SUPPORTED_TYPES:
        raise UnsupportedFileType(f"unsupported file type: .{suffix or '?'} (V1 supports pdf, txt, docx)")
    return suffix


def extract(path: str | Path, file_type: str) -> ExtractionResult:
    if file_type == "pdf":
        return _extract_pdf(Path(path))
    if file_type == "docx":
        return _extract_docx(Path(path))
    if file_type == "txt":
        return _extract_txt(Path(path))
    raise UnsupportedFileType(f"unsupported file type: {file_type}")


def _extract_pdf(path: Path) -> ExtractionResult:
    from pypdf import PdfReader

    try:
        reader = PdfReader(str(path))
    except Exception as exc:  # noqa: BLE001 - parser errors vary by file
        raise ExtractionError(f"could not read PDF: {exc}") from exc

    blocks: list[Block] = []
    for index, page in enumerate(reader.pages, start=1):
        try:
            text = page.extract_text() or ""
        except Exception:  # noqa: BLE001 - a single bad page should not kill the document
            text = ""
        text = _normalize(text)
        if text:
            blocks.append(Block(text=text, page_number=index, section_title=_guess_heading(text)))

    metadata: dict = {}
    raw = getattr(reader, "metadata", None)
    if raw:
        for key in ("title", "author", "subject", "creator"):
            value = getattr(raw, key, None)
            if value:
                metadata[key] = str(value)

    if not blocks:
        raise ExtractionError("no extractable text found (scanned PDF? OCR is deferred past V1)")
    return ExtractionResult(blocks=blocks, page_count=len(reader.pages), metadata=metadata)


def _extract_docx(path: Path) -> ExtractionResult:
    import docx

    try:
        document = docx.Document(str(path))
    except Exception as exc:  # noqa: BLE001
        raise ExtractionError(f"could not read DOCX: {exc}") from exc

    blocks: list[Block] = []
    section: str | None = None
    for paragraph in document.paragraphs:
        text = _normalize(paragraph.text)
        if not text:
            continue
        style = (paragraph.style.name or "") if paragraph.style else ""
        if style.lower().startswith("heading") or style.lower() == "title":
            section = text
            continue
        blocks.append(Block(text=text, page_number=None, section_title=section))

    metadata: dict = {}
    props = getattr(document, "core_properties", None)
    if props:
        for key in ("title", "author", "subject"):
            value = getattr(props, key, None)
            if value:
                metadata[key] = str(value)

    if not blocks:
        raise ExtractionError("no extractable text found in DOCX")
    return ExtractionResult(blocks=blocks, page_count=None, metadata=metadata)


def _extract_txt(path: Path) -> ExtractionResult:
    raw = path.read_bytes()
    for encoding in ("utf-8", "utf-16", "latin-1"):
        try:
            text = raw.decode(encoding)
            break
        except UnicodeDecodeError:
            continue
    else:  # pragma: no cover - latin-1 never fails in practice
        raise ExtractionError("could not decode text file")

    blocks: list[Block] = []
    section: str | None = None
    buffer: list[str] = []

    def flush() -> None:
        body = _normalize("\n".join(buffer))
        buffer.clear()
        if body:
            blocks.append(Block(text=body, page_number=None, section_title=section))

    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("#"):
            flush()
            section = stripped.lstrip("#").strip() or section
            continue
        buffer.append(line)
    flush()

    if not blocks:
        raise ExtractionError("text file is empty")
    return ExtractionResult(blocks=blocks, page_count=None, metadata={})


def _normalize(text: str) -> str:
    text = text.replace("\r\n", "\n").replace("\r", "\n").replace("\x00", "")
    lines = [line.rstrip() for line in text.split("\n")]
    cleaned: list[str] = []
    blank = 0
    for line in lines:
        if line:
            blank = 0
            cleaned.append(line)
        else:
            blank += 1
            if blank < 2:
                cleaned.append("")
    return "\n".join(cleaned).strip()


def _guess_heading(text: str) -> str | None:
    """Best-effort section title: the first short, title-ish line of a page."""
    for line in text.split("\n"):
        candidate = line.strip()
        if not candidate:
            continue
        if 3 <= len(candidate) <= 90 and not candidate.endswith("."):
            return candidate
        return None
    return None
