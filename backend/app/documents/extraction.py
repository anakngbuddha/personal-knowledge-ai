"""Text extraction that preserves as much structure as the parser can give us.

Anchors (page, slide, sheet + cell range, heading path) are what make citations
trustworthy, so they are captured during extraction rather than reconstructed after
chunking.

Two deliberate changes from the previous build:

* extraction works on **bytes**, not a temp file. Render's disk is ephemeral and the
  old temp-file dance existed only because the parsers were assumed to need paths.
  They do not, so the safest handling of an untrusted file is to never write it down.
* every loop checks a wall-clock `Deadline`, so one pathological file cannot pin the
  single worker forever.
"""

from __future__ import annotations

import io
from dataclasses import dataclass, field
from html.parser import HTMLParser
from pathlib import Path

from app.core.errors import ExtractionError, UnsupportedFileType
from app.core.logging import get_logger
from app.documents.anchors import Anchor
from app.documents.limits import (
    ParseLimits,
    check_html_safety,
    guard_extracted_size,
    inspect_ooxml,
)
from app.documents.sniffing import SUPPORTED_TYPES

logger = get_logger(__name__)

SUPPORTED_TYPES = SUPPORTED_TYPES  # re-exported: one source of truth

_MAX_XLSX_CELLS = 200_000
_XLSX_ROWS_PER_BLOCK = 40


@dataclass
class Block:
    """A structural unit of source text (a page, slide, sheet range, or section)."""

    text: str
    page_number: int | None = None
    section_title: str | None = None
    slide_number: int | None = None
    sheet_name: str | None = None
    cell_range: str | None = None
    heading_path: tuple[str, ...] = ()

    @property
    def anchor(self) -> Anchor:
        return Anchor(
            page_number=self.page_number,
            slide_number=self.slide_number,
            sheet_name=self.sheet_name,
            cell_range=self.cell_range,
            section_title=self.section_title,
            heading_path=tuple(self.heading_path),
        )


@dataclass
class ExtractionResult:
    blocks: list[Block] = field(default_factory=list)
    page_count: int | None = None
    metadata: dict = field(default_factory=dict)
    ocr_applied: bool = False
    warnings: list[str] = field(default_factory=list)

    @property
    def total_chars(self) -> int:
        return sum(len(b.text) for b in self.blocks)


def detect_file_type(filename: str) -> str:
    """Extension-based type, kept for scripts and tests.

    The upload path uses `app.documents.sniffing.decide_file_type`, which looks at
    the bytes. This helper trusts the name and says so.
    """
    from app.documents.sniffing import normalize_extension

    suffix = normalize_extension(filename)
    if suffix not in SUPPORTED_TYPES:
        raise UnsupportedFileType(
            f"unsupported file type: .{suffix or '?'} "
            f"(supported: {', '.join(sorted(SUPPORTED_TYPES))})"
        )
    return suffix


def extract(
    source: str | Path | bytes,
    file_type: str,
    limits: ParseLimits | None = None,
    on_progress=None,
) -> ExtractionResult:
    """Extract from raw bytes or a path. Bytes are preferred; paths are a convenience."""
    if isinstance(source, (str, Path)):
        data = Path(source).read_bytes()
    else:
        data = source

    limits = limits or ParseLimits()
    deadline = limits.deadline()

    handlers = {
        "pdf": _extract_pdf,
        "docx": _extract_docx,
        "pptx": _extract_pptx,
        "xlsx": _extract_xlsx,
        "html": _extract_html,
        "txt": _extract_text,
        "md": _extract_text,
    }
    handler = handlers.get(file_type)
    if handler is None:
        raise UnsupportedFileType(f"unsupported file type: {file_type}")

    if file_type in {"docx", "pptx", "xlsx"}:
        inspect_ooxml(data, limits)
    if file_type == "html":
        check_html_safety(data)

    if file_type == "pdf":
        result = _extract_pdf(data, limits, deadline, on_progress=on_progress)
    else:
        result = handler(data, limits, deadline)
    guard_extracted_size(result.total_chars, limits)
    if not result.blocks:
        raise ExtractionError("no extractable text found")
    return result


# --------------------------------------------------------------------------- PDF


def _extract_pdf(data: bytes, limits: ParseLimits, deadline, on_progress=None) -> ExtractionResult:
    from pypdf import PdfReader

    try:
        reader = PdfReader(io.BytesIO(data))
    except Exception as exc:  # noqa: BLE001 - parser errors vary by file
        raise ExtractionError(f"could not read PDF: {exc}") from exc

    if reader.is_encrypted:
        try:
            reader.decrypt("")
        except Exception as exc:  # noqa: BLE001
            raise ExtractionError("PDF is encrypted and cannot be read") from exc

    pages = reader.pages
    if len(pages) > limits.max_pdf_pages:
        raise ExtractionError(
            f"PDF has {len(pages)} pages, limit is {limits.max_pdf_pages}"
        )

    blocks: list[Block] = []
    empty_pages: list[int] = []
    for index, page in enumerate(pages, start=1):
        deadline.check(f"PDF page {index}")
        try:
            text = page.extract_text() or ""
        except Exception:  # noqa: BLE001 - one bad page should not kill the document
            text = ""
        text = _normalize(text)
        if text:
            blocks.append(
                Block(text=text, page_number=index, section_title=_guess_heading(text))
            )
        else:
            empty_pages.append(index)

    ocr_applied = False
    warnings: list[str] = []
    if empty_pages:
        recovered, ocr_applied = _ocr_pdf_pages(
            data, pages, empty_pages, deadline, on_progress=on_progress
        )
        if recovered:
            blocks.extend(recovered)
            blocks.sort(key=lambda b: (b.page_number or 0))
        still_empty = sorted(set(empty_pages) - {b.page_number for b in blocks})
        if still_empty:
            warnings.append(
                f"{len(still_empty)} page(s) yielded no text: {still_empty[:10]}"
            )

    if not blocks:
        raise ExtractionError(
            "This PDF is a scan and couldn't be read. Try again or upload a text version."
        )

    metadata: dict = {}
    raw = getattr(reader, "metadata", None)
    if raw:
        for key in ("title", "author", "subject", "creator"):
            try:
                value = getattr(raw, key, None)
            except Exception:  # noqa: BLE001 - malformed metadata dictionaries exist
                value = None
            if value:
                metadata[key] = str(value)[:500]

    return ExtractionResult(
        blocks=blocks,
        page_count=len(pages),
        metadata=metadata,
        ocr_applied=ocr_applied,
        warnings=warnings,
    )


def _ocr_pdf_pages(
    data: bytes,
    pages,
    page_numbers: list[int],
    deadline,
    on_progress=None,
) -> tuple[list[Block], bool]:
    """OCR pages with no text layer.

    Prefer embedded images (cheap). If a page has no image, rasterize the whole
    page with pypdfium2 (pip-only, no poppler/tesseract binary).
    """
    from app.core.config import settings
    from app.ocr.factory import get_ocr_provider

    provider = get_ocr_provider()
    if not provider.available:
        return [], False

    blocks: list[Block] = []
    budget = min(len(page_numbers), settings.ocr_max_pages)
    for index, page_number in enumerate(page_numbers[:budget], start=1):
        deadline.check(f"OCR page {page_number}")
        if on_progress:
            on_progress(f"Reading scanned page {index} of {budget}")
        page = pages[page_number - 1]
        collected: list[str] = []
        try:
            images = list(getattr(page, "images", []) or [])
        except Exception:  # noqa: BLE001
            images = []
        for image in images:
            try:
                text = provider.image_to_text(image.data)
            except Exception as exc:  # noqa: BLE001 - OCR is best effort by definition
                logger.warning("OCR failed on page %s: %s", page_number, exc)
                continue
            text = _normalize(text)
            if text:
                collected.append(text)
        if not collected:
            png = _rasterize_pdf_page(data, page_number)
            if png:
                try:
                    text = _normalize(provider.image_to_text(png))
                except Exception as exc:  # noqa: BLE001
                    logger.warning("OCR raster page %s failed: %s", page_number, exc)
                    text = ""
                if text:
                    collected.append(text)
        if collected:
            body = "\n\n".join(collected)
            blocks.append(
                Block(
                    text=body,
                    page_number=page_number,
                    section_title=_guess_heading(body),
                )
            )
    return blocks, bool(blocks)


def _rasterize_pdf_page(data: bytes, page_number: int) -> bytes | None:
    """Render one PDF page to PNG. Returns None if pypdfium2 cannot read the file."""
    from app.core.config import settings

    try:
        import pypdfium2 as pdfium
    except ImportError:
        logger.warning("pypdfium2 is not installed; cannot rasterize scanned pages")
        return None
    pdf = None
    try:
        pdf = pdfium.PdfDocument(data)
        page = pdf[page_number - 1]
        scale = max(1.0, settings.ocr_dpi / 72)
        bitmap = page.render(scale=scale)
        image = bitmap.to_pil()
        buf = io.BytesIO()
        image.save(buf, format="PNG")
        return buf.getvalue()
    except Exception as exc:  # noqa: BLE001 - some fixtures are not real PDFs
        logger.warning("could not rasterize PDF page %s: %s", page_number, exc)
        return None
    finally:
        if pdf is not None:
            try:
                pdf.close()
            except Exception:  # noqa: BLE001
                pass


# -------------------------------------------------------------------------- DOCX


def _extract_docx(data: bytes, limits: ParseLimits, deadline) -> ExtractionResult:
    import docx

    try:
        document = docx.Document(io.BytesIO(data))
    except Exception as exc:  # noqa: BLE001
        raise ExtractionError(f"could not read DOCX: {exc}") from exc

    tracker = _HeadingTracker()
    blocks: list[Block] = []

    for paragraph in document.paragraphs:
        deadline.check("DOCX paragraph")
        text = _normalize(paragraph.text)
        if not text:
            continue
        level = _docx_heading_level(paragraph)
        if level is not None:
            tracker.push(level, text)
            continue
        blocks.append(
            Block(
                text=text,
                section_title=tracker.section_title,
                heading_path=tracker.path,
            )
        )

    # Tables carry the compatibility matrices and pricing tiers that SE collateral
    # lives on. The previous build dropped them silently.
    for table_index, table in enumerate(document.tables, start=1):
        deadline.check("DOCX table")
        rendered = _render_table([[cell.text for cell in row.cells] for row in table.rows])
        if rendered:
            blocks.append(
                Block(
                    text=rendered,
                    section_title=tracker.section_title or f"Table {table_index}",
                    heading_path=tracker.path or (f"Table {table_index}",),
                )
            )

    metadata: dict = {}
    props = getattr(document, "core_properties", None)
    if props:
        for key in ("title", "author", "subject"):
            value = getattr(props, key, None)
            if value:
                metadata[key] = str(value)[:500]

    if not blocks:
        raise ExtractionError("no extractable text found in DOCX")
    return ExtractionResult(blocks=blocks, page_count=None, metadata=metadata)


def _docx_heading_level(paragraph) -> int | None:
    style = ((paragraph.style.name if paragraph.style else "") or "").strip().lower()
    if style == "title":
        return 0
    if style.startswith("heading"):
        tail = style.replace("heading", "").strip()
        return int(tail) if tail.isdigit() else 1
    return None


# -------------------------------------------------------------------------- PPTX


def _extract_pptx(data: bytes, limits: ParseLimits, deadline) -> ExtractionResult:
    from pptx import Presentation

    try:
        presentation = Presentation(io.BytesIO(data))
    except Exception as exc:  # noqa: BLE001
        raise ExtractionError(f"could not read PPTX: {exc}") from exc

    blocks: list[Block] = []
    for index, slide in enumerate(presentation.slides, start=1):
        deadline.check(f"slide {index}")
        title = _slide_title(slide)
        body: list[str] = []
        for shape in slide.shapes:
            if getattr(shape, "has_table", False):
                rendered = _render_table(
                    [[cell.text for cell in row.cells] for row in shape.table.rows]
                )
                if rendered:
                    body.append(rendered)
                continue
            if not getattr(shape, "has_text_frame", False):
                continue
            text = _normalize(shape.text_frame.text)
            if text and text != title:
                body.append(text)

        notes = ""
        try:
            if slide.has_notes_slide:
                notes = _normalize(slide.notes_slide.notes_text_frame.text)
        except Exception:  # noqa: BLE001 - notes are optional and often malformed
            notes = ""
        if notes:
            body.append(f"[speaker notes]\n{notes}")

        combined = _normalize("\n\n".join(part for part in body if part))
        if not combined and not title:
            continue
        blocks.append(
            Block(
                text=combined or title,
                slide_number=index,
                section_title=title or None,
                heading_path=(title,) if title else (),
            )
        )

    metadata: dict = {}
    props = getattr(presentation, "core_properties", None)
    if props:
        for key in ("title", "author", "subject"):
            value = getattr(props, key, None)
            if value:
                metadata[key] = str(value)[:500]
    metadata["slide_count"] = len(presentation.slides)

    if not blocks:
        raise ExtractionError("no extractable text found in PPTX")
    return ExtractionResult(blocks=blocks, page_count=None, metadata=metadata)


def _slide_title(slide) -> str:
    try:
        placeholder = slide.shapes.title
    except Exception:  # noqa: BLE001
        placeholder = None
    if placeholder is None:
        return ""
    return _normalize(placeholder.text or "")


# -------------------------------------------------------------------------- XLSX


def _extract_xlsx(data: bytes, limits: ParseLimits, deadline) -> ExtractionResult:
    from openpyxl import load_workbook
    from openpyxl.utils import get_column_letter

    try:
        workbook = load_workbook(io.BytesIO(data), read_only=True, data_only=True)
    except Exception as exc:  # noqa: BLE001
        raise ExtractionError(f"could not read XLSX: {exc}") from exc

    blocks: list[Block] = []
    cells_seen = 0
    sheet_names = [sheet.title for sheet in workbook.worksheets]
    try:
        for sheet in workbook.worksheets:
            deadline.check(f"sheet {sheet.title}")
            buffer: list[tuple[int, list[str]]] = []

            def flush(sheet_title: str, rows: list[tuple[int, list[str]]]) -> None:
                if not rows:
                    return
                width = max(len(values) for _, values in rows)
                first_row, last_row = rows[0][0], rows[-1][0]
                cell_range = f"A{first_row}:{get_column_letter(max(width, 1))}{last_row}"
                rendered = _render_table([values for _, values in rows])
                if rendered:
                    blocks.append(
                        Block(
                            text=rendered,
                            sheet_name=sheet_title,
                            cell_range=cell_range,
                            section_title=sheet_title,
                            heading_path=(sheet_title,),
                        )
                    )

            for row_index, row in enumerate(sheet.iter_rows(values_only=True), start=1):
                cells_seen += len(row)
                if cells_seen > _MAX_XLSX_CELLS:
                    raise ExtractionError(
                        f"workbook exceeds the {_MAX_XLSX_CELLS} cell extraction limit"
                    )
                values = ["" if value is None else str(value).strip() for value in row]
                if any(values):
                    buffer.append((row_index, values))
                if len(buffer) >= _XLSX_ROWS_PER_BLOCK:
                    deadline.check(f"sheet {sheet.title}")
                    flush(sheet.title, buffer)
                    buffer = []
            flush(sheet.title, buffer)
    finally:
        workbook.close()

    if not blocks:
        raise ExtractionError("no extractable text found in XLSX")
    return ExtractionResult(
        blocks=blocks, page_count=None, metadata={"sheet_names": sheet_names}
    )


# -------------------------------------------------------------------------- HTML


class _HtmlTextExtractor(HTMLParser):
    """Stdlib parser: tolerant, and it never resolves external entities or DTDs."""

    _SKIP = {"script", "style", "noscript", "template", "svg"}
    _BREAK = {"p", "div", "br", "li", "tr", "section", "article", "blockquote", "td", "th"}
    _HEADINGS = {f"h{level}": level for level in range(1, 7)}

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.blocks: list[Block] = []
        self.title = ""
        self._skip_depth = 0
        self._buffer: list[str] = []
        self._tracker = _HeadingTracker()
        self._in_title = False
        self._heading_level: int | None = None
        self._heading_text: list[str] = []

    def handle_starttag(self, tag: str, attrs) -> None:
        tag = tag.lower()
        if tag in self._SKIP:
            self._skip_depth += 1
            return
        if tag == "title":
            self._in_title = True
            return
        if tag in self._HEADINGS:
            self._flush()
            self._heading_level = self._HEADINGS[tag]
            self._heading_text = []
            return
        if tag in self._BREAK:
            self._buffer.append("\n")

    def handle_endtag(self, tag: str) -> None:
        tag = tag.lower()
        if tag in self._SKIP:
            self._skip_depth = max(0, self._skip_depth - 1)
            return
        if tag == "title":
            self._in_title = False
            return
        if tag in self._HEADINGS and self._heading_level is not None:
            heading = _normalize(" ".join(self._heading_text))
            if heading:
                self._tracker.push(self._heading_level, heading)
            self._heading_level = None
            self._heading_text = []

    def handle_data(self, data: str) -> None:
        if self._skip_depth:
            return
        if self._in_title:
            self.title += data
            return
        if self._heading_level is not None:
            self._heading_text.append(data)
            return
        self._buffer.append(data)

    def _flush(self) -> None:
        text = _normalize("".join(self._buffer))
        self._buffer = []
        if text:
            self.blocks.append(
                Block(
                    text=text,
                    section_title=self._tracker.section_title,
                    heading_path=self._tracker.path,
                )
            )

    def close(self) -> None:  # type: ignore[override]
        super().close()
        self._flush()


def _extract_html(data: bytes, limits: ParseLimits, deadline) -> ExtractionResult:
    text = _decode(data)
    parser = _HtmlTextExtractor()
    try:
        parser.feed(text)
        parser.close()
    except Exception as exc:  # noqa: BLE001
        raise ExtractionError(f"could not parse HTML: {exc}") from exc
    deadline.check("HTML parse")
    if not parser.blocks:
        raise ExtractionError("no extractable text found in HTML")
    metadata = {"title": _normalize(parser.title)} if parser.title.strip() else {}
    return ExtractionResult(blocks=parser.blocks, page_count=None, metadata=metadata)


# ----------------------------------------------------------------------- TXT / MD


def _extract_text(data: bytes, limits: ParseLimits, deadline) -> ExtractionResult:
    text = _decode(data)
    tracker = _HeadingTracker()
    blocks: list[Block] = []
    buffer: list[str] = []

    def flush() -> None:
        body = _normalize("\n".join(buffer))
        buffer.clear()
        if body:
            blocks.append(
                Block(
                    text=body,
                    section_title=tracker.section_title,
                    heading_path=tracker.path,
                )
            )

    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("#"):
            level = len(stripped) - len(stripped.lstrip("#"))
            heading = stripped.lstrip("#").strip()
            if heading:
                flush()
                tracker.push(level, heading)
                continue
        buffer.append(line)
    flush()

    if not blocks:
        raise ExtractionError("text file is empty")
    return ExtractionResult(blocks=blocks, page_count=None, metadata={})


# ------------------------------------------------------------------------ helpers


class _HeadingTracker:
    """Maintains the current heading path, e.g. ('Licensing', 'Enterprise tier')."""

    def __init__(self) -> None:
        self._stack: list[tuple[int, str]] = []

    def push(self, level: int, text: str) -> None:
        while self._stack and self._stack[-1][0] >= level:
            self._stack.pop()
        self._stack.append((level, text))

    @property
    def path(self) -> tuple[str, ...]:
        return tuple(text for _, text in self._stack)

    @property
    def section_title(self) -> str | None:
        return self._stack[-1][1] if self._stack else None


def _render_table(rows: list[list[str]]) -> str:
    """Pipe-delimited rows. Readable to a human, chunkable, and cheap to embed."""
    cleaned: list[str] = []
    seen_blank = False
    for row in rows:
        cells = [" ".join(str(cell or "").split()) for cell in row]
        if not any(cells):
            seen_blank = True
            continue
        if seen_blank and cleaned:
            cleaned.append("")
            seen_blank = False
        cleaned.append(" | ".join(cells))
    return _normalize("\n".join(cleaned))


def _decode(data: bytes) -> str:
    if data[:3] == b"\xef\xbb\xbf":
        data = data[3:]
    for encoding in ("utf-8", "utf-16", "latin-1"):
        try:
            return data.decode(encoding)
        except UnicodeDecodeError:
            continue
    raise ExtractionError("could not decode text content")


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
