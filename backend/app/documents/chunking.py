"""Deterministic, structure-aware chunking.

Rules kept intentionally simple until the evaluation set says otherwise:
  * chunks never span a page or section boundary, so a citation is always precise
  * splits prefer paragraph, then line, then sentence boundaries
  * a fixed character overlap carries context across boundaries
"""

from dataclasses import dataclass
from itertools import groupby

from app.core.config import settings
from app.documents.extraction import Block


@dataclass
class Chunk:
    text: str
    chunk_index: int
    page_number: int | None
    section_title: str | None
    start_offset: int
    end_offset: int


def chunk_blocks(
    blocks: list[Block],
    chunk_size: int | None = None,
    chunk_overlap: int | None = None,
) -> list[Chunk]:
    size = chunk_size or settings.chunk_size
    overlap = chunk_overlap or settings.chunk_overlap
    if size <= 0:
        raise ValueError("chunk_size must be positive")
    if overlap < 0 or overlap >= size:
        raise ValueError("chunk_overlap must be >= 0 and < chunk_size")

    chunks: list[Chunk] = []
    offset = 0
    index = 0

    for key, group in groupby(blocks, key=lambda b: (b.page_number, b.section_title)):
        page_number, section_title = key
        text = "\n\n".join(b.text.strip() for b in group if b.text.strip())
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
                    page_number=page_number,
                    section_title=section_title,
                    start_offset=offset + start,
                    end_offset=offset + end,
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
