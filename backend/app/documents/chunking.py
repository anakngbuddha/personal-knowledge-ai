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
section" for the formats added in this phase. It is now the full anchor.
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

    for _, group in groupby(blocks, key=lambda block: block.anchor.key()):
        members = list(group)
        anchor = members[0].anchor
        text = "\n\n".join(block.text.strip() for block in members if block.text.strip())
        if not text:
            continue
        for start, end in _windows(text, size, overlap):
            piece = text[start:end].strip()
            if not piece:
                continue
            chunks.append(
                Chunk(
                    text=piece,
                    chunk_index=index,
                    start_offset=offset + start,
                    end_offset=offset + end,
                    anchor=anchor,
                )
            )
            index += 1
        offset += len(text) + 2  # the "\n\n" joiner between groups

    return chunks


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
