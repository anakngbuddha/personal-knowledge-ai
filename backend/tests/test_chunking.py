from app.documents.chunking import chunk_blocks
from app.documents.extraction import Block


def test_chunks_do_not_span_pages():
    blocks = [
        Block(text="alpha " * 100, page_number=1, section_title="One"),
        Block(text="beta " * 100, page_number=2, section_title="Two"),
    ]
    chunks = chunk_blocks(blocks, chunk_size=200, chunk_overlap=20)
    pages = {c.page_number for c in chunks}
    assert pages == {1, 2}
    for chunk in chunks:
        assert chunk.section_title in {"One", "Two"}


def test_chunk_indexes_are_sequential_and_deterministic():
    blocks = [Block(text="gamma " * 400, page_number=1)]
    first = chunk_blocks(blocks, chunk_size=300, chunk_overlap=50)
    second = chunk_blocks(blocks, chunk_size=300, chunk_overlap=50)
    assert [c.text for c in first] == [c.text for c in second]
    assert [c.chunk_index for c in first] == list(range(len(first)))
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
