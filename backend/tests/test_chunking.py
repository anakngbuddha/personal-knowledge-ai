"""Chunking. Determinism first: the Phase 2 baseline is only comparable if identical
input yields byte-identical chunks."""

import pytest

from app.documents.chunking import chunk_blocks
from app.documents.extraction import Block


def test_chunks_do_not_span_pages():
    blocks = [
        Block(text="alpha " * 100, page_number=1, section_title="One"),
        Block(text="beta " * 100, page_number=2, section_title="Two"),
    ]
    chunks = chunk_blocks(blocks, chunk_size=200, chunk_overlap=20)
    assert {chunk.page_number for chunk in chunks} == {1, 2}
    for chunk in chunks:
        assert chunk.section_title in {"One", "Two"}


def test_chunks_do_not_span_slides():
    blocks = [
        Block(text="slide one " * 60, slide_number=1, section_title="Intro"),
        Block(text="slide two " * 60, slide_number=2, section_title="Architecture"),
    ]
    chunks = chunk_blocks(blocks, chunk_size=200, chunk_overlap=20)
    assert {chunk.slide_number for chunk in chunks} == {1, 2}
    assert all(chunk.page_number is None for chunk in chunks)


def test_chunks_do_not_span_sheet_ranges():
    blocks = [
        Block(text="pricing rows " * 60, sheet_name="Pricing", cell_range="A1:C40"),
        Block(text="eol rows " * 60, sheet_name="EOL", cell_range="A1:B10"),
    ]
    chunks = chunk_blocks(blocks, chunk_size=200, chunk_overlap=20)
    assert {(chunk.sheet_name, chunk.cell_range) for chunk in chunks} == {
        ("Pricing", "A1:C40"),
        ("EOL", "A1:B10"),
    }


def test_chunks_do_not_span_heading_paths():
    """The old grouping key was (page, section), which collapsed every heading-path
    document into one group. This is the regression test for that."""
    blocks = [
        Block(text="licensing body " * 40, heading_path=("Licensing",), section_title="Licensing"),
        Block(
            text="enterprise body " * 40,
            heading_path=("Licensing", "Enterprise"),
            section_title="Enterprise",
        ),
    ]
    chunks = chunk_blocks(blocks, chunk_size=200, chunk_overlap=20)
    paths = {chunk.heading_path for chunk in chunks}
    assert paths == {("Licensing",), ("Licensing", "Enterprise")}


def test_chunk_indexes_are_sequential_and_deterministic():
    blocks = [Block(text="gamma " * 400, page_number=1)]
    first = chunk_blocks(blocks, chunk_size=300, chunk_overlap=50)
    second = chunk_blocks(blocks, chunk_size=300, chunk_overlap=50)
    assert [chunk.text for chunk in first] == [chunk.text for chunk in second]
    assert [chunk.chunk_index for chunk in first] == list(range(len(first)))
    assert len(first) > 1


def test_offsets_are_monotonic():
    blocks = [Block(text="delta " * 300, page_number=1)]
    chunks = chunk_blocks(blocks, chunk_size=250, chunk_overlap=40)
    for previous, current in zip(chunks, chunks[1:], strict=False):
        assert current.start_offset > previous.start_offset
        assert current.end_offset >= previous.end_offset


def test_short_document_produces_single_chunk():
    chunks = chunk_blocks([Block(text="one small paragraph.", page_number=1)], 500, 50)
    assert len(chunks) == 1
    assert chunks[0].text == "one small paragraph."


def test_zero_overlap_is_honoured_not_replaced_by_the_default():
    """`overlap = chunk_overlap or settings.chunk_overlap` silently turned an explicit
    0 into 150, which quietly broke the zero-overlap arm of a chunking experiment."""
    blocks = [Block(text="epsilon " * 200, page_number=1)]
    zero = chunk_blocks(blocks, chunk_size=200, chunk_overlap=0)
    overlapping = chunk_blocks(blocks, chunk_size=200, chunk_overlap=100)
    # Zero overlap means windows are contiguous; a silently applied default would
    # make them overlap exactly like the 100 case.
    assert zero[1].start_offset == zero[0].end_offset
    assert overlapping[1].start_offset < overlapping[0].end_offset


def test_invalid_parameters_are_rejected():
    blocks = [Block(text="x " * 50)]
    with pytest.raises(ValueError):
        chunk_blocks(blocks, chunk_size=0)
    with pytest.raises(ValueError):
        chunk_blocks(blocks, chunk_size=100, chunk_overlap=100)
    with pytest.raises(ValueError):
        chunk_blocks(blocks, chunk_size=100, chunk_overlap=-1)


def test_anchor_label_is_human_readable():
    blocks = [
        Block(text="a", page_number=3, section_title="Gaps"),
        Block(text="b", slide_number=7, section_title="Architecture"),
        Block(text="c", sheet_name="Pricing", cell_range="A1:C9"),
        Block(text="d", heading_path=("Licensing", "Tiers")),
    ]
    labels = [chunk.anchor.label() for chunk in chunk_blocks(blocks, 500, 0)]
    assert labels == ["p. 3 - Gaps", "slide 7 - Architecture", "Pricing!A1:C9", "Licensing > Tiers"]
