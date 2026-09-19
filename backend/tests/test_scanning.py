"""Malware scanning. The heuristic backend is not an antivirus; these tests assert
exactly what it does claim to catch, and that nothing clean is refused."""

import pytest

from app.core.errors import MalwareDetected
from app.documents.scanning import HeuristicScanner, NullScanner, scan_or_raise
from tests import fixtures as F


@pytest.fixture
def scanner():
    return HeuristicScanner()


def test_clean_files_pass(scanner):
    for data, file_type in (
        (F.make_docx(), "docx"),
        (F.make_pptx(), "pptx"),
        (F.make_xlsx(), "xlsx"),
        (F.make_pdf([["clean"]]), "pdf"),
        (F.MARKDOWN, "md"),
        (F.HTML, "html"),
    ):
        result = scanner.scan(data, file_type)
        assert result.clean, (file_type, result.findings)


def test_office_macros_are_refused(scanner):
    result = scanner.scan(F.make_macro_docx(), "docx")
    assert not result.clean
    assert any("macro" in finding.lower() for finding in result.findings)


def test_pdf_javascript_and_launch_actions_are_refused(scanner):
    result = scanner.scan(F.make_pdf_with_javascript(), "pdf")
    assert not result.clean
    assert any("JavaScript" in finding for finding in result.findings)


def test_embedded_executable_is_refused(scanner):
    payload = F.MARKDOWN + b"\x4d\x5a\x90\x00\x03" + b"\x00" * 128
    result = scanner.scan(payload, "md")
    assert not result.clean


def test_external_relationship_target_is_refused(scanner):
    import io
    import zipfile

    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("word/document.xml", b"<w:document/>")
        archive.writestr(
            "word/_rels/document.xml.rels",
            b'<Relationships><Relationship Id="r1" Target="http://evil.example.com/x" '
            b'TargetMode="External"/></Relationships>',
        )
    result = scanner.scan(buffer.getvalue(), "docx")
    assert not result.clean
    assert any("external" in finding.lower() for finding in result.findings)


def test_scan_or_raise_converts_a_finding_into_an_error():
    with pytest.raises(MalwareDetected):
        scan_or_raise(F.make_macro_docx(), "docx", HeuristicScanner())


def test_disabled_scanner_is_recorded_not_hidden():
    result = NullScanner().scan(F.make_macro_docx(), "docx")
    assert result.clean is True
    # The audit trail must say scanning did not happen, so a document is never
    # mistaken for one that passed a scan.
    assert result.backend == "none"
    assert result.findings == ["scanning disabled"]
