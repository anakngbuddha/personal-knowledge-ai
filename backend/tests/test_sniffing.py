"""Content sniffing: the file is what its bytes say, not what its name claims."""

import pytest

from app.core.errors import UnsupportedFileType
from app.documents.sniffing import decide_file_type, normalize_extension, sniff
from tests import fixtures as F


def test_sniffs_every_supported_format():
    assert sniff(F.make_pdf([["hello"]])).file_type == "pdf"
    assert sniff(F.make_docx()).file_type == "docx"
    assert sniff(F.make_pptx()).file_type == "pptx"
    assert sniff(F.make_xlsx()).file_type == "xlsx"
    assert sniff(F.HTML).file_type == "html"
    assert sniff(F.MARKDOWN).file_type == "txt"  # md and txt are byte-identical


def test_content_beats_the_extension():
    decision = decide_file_type("quarterly-deck.pdf", F.make_pptx())
    assert decision.file_type == "pptx"
    assert decision.extension_mismatch is True
    assert decision.declared_extension == "pdf"


def test_markdown_extension_is_honoured_because_bytes_cannot_tell():
    decision = decide_file_type("notes.md", F.MARKDOWN)
    assert decision.file_type == "md"
    assert decision.extension_mismatch is False


def test_executables_and_archives_are_named_in_the_error():
    for payload, expected in (
        (b"\x7fELF\x02\x01\x01" + b"\x00" * 64, "ELF"),
        (b"MZ\x90\x00" + b"\x00" * 64, "Windows executable"),
        (b"\x1f\x8b\x08\x00" + b"\x00" * 64, "gzip"),
        (b"{\\rtf1\\ansi", "RTF"),
        (b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1", "OLE2"),
    ):
        with pytest.raises(UnsupportedFileType) as excinfo:
            decide_file_type("payload.docx", payload)
        assert expected.lower() in str(excinfo.value).lower()


def test_plain_zip_is_refused_even_though_it_is_a_valid_container():
    import io
    import zipfile

    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("readme.txt", b"hello")
    with pytest.raises(UnsupportedFileType):
        decide_file_type("collateral.docx", buffer.getvalue())


def test_empty_file_is_refused():
    with pytest.raises(UnsupportedFileType):
        decide_file_type("empty.txt", b"")


def test_extension_aliases():
    assert normalize_extension("a.HTM") == "html"
    assert normalize_extension("a.markdown") == "md"
    assert normalize_extension("a.TEXT") == "txt"
