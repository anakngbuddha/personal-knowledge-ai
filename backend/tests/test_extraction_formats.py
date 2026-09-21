"""Golden extraction tests: one fixture per format, plus one malformed file per format.

The assertions are about **anchors**, not word counts. A page or slide number that
resolves to the right place is the entire reason this layer exists.
"""

import pytest

from app.core.errors import ExtractionError, UnsafeFile, UnsupportedFileType
from app.documents.chunking import chunk_blocks
from app.documents.extraction import detect_file_type, extract
from tests import fixtures as F


def test_pdf_pages_become_page_anchors():
    pdf = F.make_pdf(
        [["Integration Gaps", "VPN required between sites."], ["Support Path", "Vendor owned."]],
        title="Gap Report",
    )
    result = extract(pdf, "pdf")
    assert result.page_count == 2
    assert [block.page_number for block in result.blocks] == [1, 2]
    assert "VPN required" in result.blocks[0].text
    assert result.metadata["title"] == "Gap Report"
    assert result.ocr_applied is False


def test_pdf_chunks_carry_the_page_anchor():
    pdf = F.make_pdf([["Page one body text."], ["Page two body text."]])
    chunks = chunk_blocks(extract(pdf, "pdf").blocks, 400, 50)
    assert {chunk.page_number for chunk in chunks} == {1, 2}
    assert all(chunk.anchor.label().startswith("p. ") for chunk in chunks)


def test_docx_builds_a_heading_path_and_keeps_tables():
    result = extract(F.make_docx(), "docx")
    paths = [block.heading_path for block in result.blocks]
    assert ("Licensing",) in paths
    assert ("Licensing", "Enterprise tier") in paths
    table_text = "\n".join(block.text for block in result.blocks)
    # Tables carry the compatibility and pricing data; dropping them was a real bug.
    assert "Max nodes" in table_text
    assert "OrbitCloud | Enterprise | 64" in table_text


def test_pptx_slides_become_slide_anchors_with_notes_and_tables():
    result = extract(F.make_pptx(), "pptx")
    assert [block.slide_number for block in result.blocks] == [1, 2]
    assert result.blocks[0].section_title == "Reference Architecture"
    assert "speaker notes" in result.blocks[0].text
    assert "conflicts with LegacyEdge" in result.blocks[1].text
    assert result.blocks[1].anchor.label().startswith("slide 2")


def test_xlsx_rows_become_sheet_and_cell_anchors():
    result = extract(F.make_xlsx(), "xlsx")
    anchors = {(block.sheet_name, block.cell_range) for block in result.blocks}
    assert ("Pricing", "A1:C3") in anchors
    assert ("EOL", "A1:B2") in anchors
    pricing = next(block for block in result.blocks if block.sheet_name == "Pricing")
    assert "OrbitCloud | 1200 | 960" in pricing.text
    assert pricing.anchor.label() == "Pricing!A1:C3"
    assert result.metadata["sheet_names"] == ["Pricing", "EOL"]


def test_html_drops_script_and_style_and_keeps_heading_path():
    result = extract(F.HTML, "html")
    text = "\n".join(block.text for block in result.blocks)
    assert "console.log" not in text
    assert "display:none" not in text
    assert "10GbE network" in text
    assert ("VaultStore", "Prerequisites") in [block.heading_path for block in result.blocks]
    assert result.metadata["title"] == "VaultStore Datasheet"


def test_markdown_heading_path_is_hierarchical():
    result = extract(F.MARKDOWN, "md")
    assert [block.heading_path for block in result.blocks] == [
        ("OrbitCloud",),
        ("OrbitCloud", "Capabilities"),
        ("OrbitCloud", "Capabilities", "Support path"),
    ]


@pytest.mark.parametrize(
    ("file_type", "builder"),
    [
        ("pdf", lambda: F.make_truncated(F.make_pdf([["a"]]))),
        ("docx", lambda: F.make_truncated(F.make_docx())),
        ("pptx", lambda: F.make_truncated(F.make_pptx())),
        ("xlsx", lambda: F.make_truncated(F.make_xlsx())),
        ("html", lambda: b"<html><head><title>t</title></head><body></body></html>"),
        ("md", lambda: b"   \n\n  \n"),
    ],
)
def test_one_malformed_file_per_format_fails_explainably(file_type, builder):
    """Every failure must be a named application error with a readable message, never
    a bare parser traceback: the document row stores this string."""
    with pytest.raises((ExtractionError, UnsafeFile)) as excinfo:
        extract(builder(), file_type)
    assert str(excinfo.value)


def test_scanned_pdf_says_what_to_do_about_it():
    # A PDF with pages but no text layer, and OCR disabled.
    blank = F.make_pdf([[""], [""]])
    with pytest.raises(ExtractionError) as excinfo:
        extract(blank, "pdf")
    message = str(excinfo.value).lower()
    assert "scan" in message
    assert "text version" in message


def test_fake_ocr_recovers_text_from_a_rasterized_page(monkeypatch):
    from app.ocr.factory import get_ocr_provider
    from app.ocr.fake import FakeOcrProvider

    monkeypatch.setattr(
        "app.documents.extraction._rasterize_pdf_page",
        lambda data, page_number: b"\x89PNG-fake-page",
    )
    monkeypatch.setattr("app.ocr.factory.get_ocr_provider", lambda: FakeOcrProvider("Jabra Speak 750"))
    get_ocr_provider.cache_clear()
    blank = F.make_pdf([[""]])
    result = extract(blank, "pdf")
    assert result.ocr_applied is True
    assert "Jabra Speak 750" in result.blocks[0].text


def test_detect_file_type_covers_the_new_formats():
    for name, expected in [
        ("Lecture 03.PDF", "pdf"),
        ("deck.pptx", "pptx"),
        ("pricing.XLSX", "xlsx"),
        ("page.htm", "html"),
        ("notes.md", "md"),
        ("notes.txt", "txt"),
        ("paper.docx", "docx"),
    ]:
        assert detect_file_type(name) == expected
    with pytest.raises(UnsupportedFileType):
        detect_file_type("image.png")
