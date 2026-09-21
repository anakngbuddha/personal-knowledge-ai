"""Deterministic, structure-aware chunking.

Rules kept intentionally simple until the evaluation set says otherwise:
  * chunks never span an **anchor** boundary (page, slide, sheet range, heading
    path), so a citation is always precise
  * splits prefer paragraph, then line, then sentence boundaries
  * a fixed character overlap carries context across boundaries
  * identical input produces byte-identical output, so retrieval evaluation stays
    comparable across runs

Changed from the previous build: the grouping key was `(page_number, section_title)`,
which collapsed every slide, sheet range, and heading path into "no page, no
section" for the formats added in that phase. It is now the full anchor.

Added in 2.3, three things that all come from the same observation: a chunk that lost
its surroundings answers badly.

1. **Tables stay whole.** A spec sheet or price table split mid-row produces chunks
   where the header says one thing and the numbers belong to something else, which is
   the single worst failure mode for a salesperson quoting a spec. A table-shaped
   anchor group is emitted as one chunk up to `chunk_table_max_multiple` x chunk size,
   and only falls back to windowing past that.
2. **Every child names its section.** The heading is prefixed to the child text, so
   keyword search can match "Licensing" even when the sentence never repeats the word.
3. **Parent and child.** The child is what gets embedded and matched; the parent is the
   whole anchor group, carried alongside so generation can prompt with the full section
   after matching on the narrow piece. The parent lives in chunk metadata rather than a
   new column, which keeps this change migration-free.
"""

from __future__ import annotations

from dataclasses import dataclass
from itertools import groupby

from app.core.config import settings
from app.documents.anchors import Anchor
from app.documents.extraction import Block


@dataclass
class Chunk:
    text: str
    chunk_index: int
    start_offset: int
    end_offset: int
    anchor: Anchor = Anchor()
    # 2.3: the whole anchor group this child came from. Empty when parent/child is off
    # or when the child already is the whole group.
    parent_text: str = ""
    parent_index: int = 0
    is_table: bool = False
    heading: str | None = None

    # Flat accessors so callers (and the ORM mapping) do not have to reach through
    # the anchor for the two fields that existed before this phase.
    @property
    def page_number(self) -> int | None:
        return self.anchor.page_number

    @property
    def section_title(self) -> str | None:
        return self.anchor.section_title

    @property
    def slide_number(self) -> int | None:
        return self.anchor.slide_number

    @property
    def sheet_name(self) -> str | None:
        return self.anchor.sheet_name

    @property
    def cell_range(self) -> str | None:
        return self.anchor.cell_range

    @property
    def heading_path(self) -> tuple[str, ...]:
        return self.anchor.heading_path


def chunk_blocks(
    blocks: list[Block],
    chunk_size: int | None = None,
    chunk_overlap: int | None = None,
) -> list[Chunk]:
    # `or` would have silently turned an explicit 0 overlap into the configured
    # default. Zero overlap is a legitimate experiment for the Phase 2 baseline.
    size = settings.chunk_size if chunk_size is None else chunk_size
    overlap = settings.chunk_overlap if chunk_overlap is None else chunk_overlap
    if size <= 0:
        raise ValueError("chunk_size must be positive")
    if overlap < 0 or overlap >= size:
        raise ValueError("chunk_overlap must be >= 0 and < chunk_size")

    chunks: list[Chunk] = []
    offset = 0
    index = 0
    group_index = 0

    for _, group in groupby(blocks, key=lambda block: block.anchor.key()):
        members = list(group)
        anchor = members[0].anchor
        text = "\n\n".join(block.text.strip() for block in members if block.text.strip())
        if not text:
            continue

        heading = _heading_for(anchor)
        table_like = _looks_like_table(anchor, text)
        keep_whole = (
            table_like
            and settings.chunk_keep_tables_whole
            and len(text) <= size * max(1, settings.chunk_table_max_multiple)
        )
        windows = [(0, len(text))] if keep_whole else _windows(text, size, overlap)

        for start, end in windows:
            piece = text[start:end].strip()
            if not piece:
                continue
            body = _with_heading(heading, piece)
            # A child that already is the whole group has no parent to add.
            parent = "" if (start, end) == (0, len(text)) else text
            chunks.append(
                Chunk(
                    text=body,
                    chunk_index=index,
                    start_offset=offset + start,
                    end_offset=offset + end,
                    anchor=anchor,
                    parent_text=parent if settings.chunk_parent_child_enabled else "",
                    parent_index=group_index,
                    is_table=table_like,
                    heading=heading,
                )
            )
            index += 1

        offset += len(text) + 2  # the "\n\n" joiner between groups
        group_index += 1

    return chunks


def _heading_for(anchor: Anchor) -> str | None:
    if anchor.heading_path:
        return " > ".join(anchor.heading_path)
    if anchor.section_title:
        return anchor.section_title
    if anchor.sheet_name:
        return anchor.sheet_name
    return None


def _with_heading(heading: str | None, piece: str) -> str:
    """Prefix the section heading so the child can be matched on it.

    Skipped when there is no heading, when the feature is off, or when the text already
    opens with the heading, so a document whose body repeats its own headings is not
    doubled up.
    """
    if not heading or not settings.chunk_prepend_heading:
        return piece
    if piece.lstrip().lower().startswith(heading.lower()):
        return piece
    return f"{heading}\n\n{piece}"


# A row-shaped line: pipes, tabs, or two or more columns separated by run-on spaces.
def _is_row(line: str) -> bool:
    stripped = line.strip()
    if not stripped:
        return False
    if "|" in stripped or "\t" in stripped:
        return True
    return len([part for part in stripped.split("  ") if part.strip()]) >= 3


def _looks_like_table(anchor: Anchor, text: str) -> bool:
    """Spreadsheet ranges are tables by construction; everything else is shape-tested."""
    if anchor.sheet_name or anchor.cell_range:
        return True
    lines = [line for line in text.splitlines() if line.strip()]
    if len(lines) < 3:
        return False
    rows = sum(1 for line in lines if _is_row(line))
    return rows >= max(3, (len(lines) * 2) // 3)


def _windows(text: str, size: int, overlap: int) -> list[tuple[int, int]]:
    windows: list[tuple[int, int]] = []
    length = len(text)
    start = 0
    while start < length:
        end = min(start + size, length)
        if end < length:
            window = text[start:end]
            cut = max(window.rfind("\n\n"), window.rfind("\n"), window.rfind(". "))
            if cut > size // 2:
                end = start + cut + 1
        windows.append((start, end))
        if end >= length:
            break
        start = max(end - overlap, start + 1)
    return windows
