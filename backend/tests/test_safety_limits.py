"""Pre-parse safety limits. These are the controls, so these are the tests."""

import time

import pytest

from app.core.errors import ExtractionTimeout, UnsafeFile
from app.documents.limits import Deadline, ParseLimits, check_html_safety, guard_extracted_size, inspect_ooxml
from tests import fixtures as F


def test_clean_ooxml_passes_and_reports_its_shape():
    report = inspect_ooxml(F.make_docx())
    assert report.entries > 0
    assert report.declares_dtd is False
    assert report.uncompressed_bytes > 0


def test_zip_bomb_is_refused_before_any_parser_runs():
    with pytest.raises(UnsafeFile, match="zip bomb"):
        inspect_ooxml(F.make_zip_bomb(600))


def test_entry_count_limit():
    import io
    import zipfile

    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("word/document.xml", b"<w:document/>")
        for index in range(50):
            archive.writestr(f"word/media/{index}.bin", b"x")
    with pytest.raises(UnsafeFile, match="entries"):
        inspect_ooxml(buffer.getvalue(), ParseLimits(max_archive_entries=10))


def test_compression_ratio_limit():
    with pytest.raises(UnsafeFile):
        inspect_ooxml(
            F.make_zip_bomb(200),
            ParseLimits(max_uncompressed_bytes=10**12, max_compression_ratio=5.0),
        )


def test_xxe_declaration_is_refused():
    with pytest.raises(UnsafeFile, match="DOCTYPE or ENTITY"):
        inspect_ooxml(F.make_xxe_docx())


def test_path_traversal_entry_is_refused():
    with pytest.raises(UnsafeFile, match="escapes the package root"):
        inspect_ooxml(F.make_traversal_docx())


def test_html_entity_declaration_is_refused():
    billion_laughs = (
        b'<!DOCTYPE lolz [<!ENTITY lol "lol"><!ENTITY lol2 "&lol;&lol;">]>'
        b"<html><body>&lol2;</body></html>"
    )
    with pytest.raises(UnsafeFile, match="ENTITY"):
        check_html_safety(billion_laughs)
    # A normal doctype is fine; every real HTML page has one.
    check_html_safety(F.HTML)


def test_extracted_size_cap():
    guard_extracted_size(10, ParseLimits(max_extracted_chars=100))
    with pytest.raises(UnsafeFile):
        guard_extracted_size(101, ParseLimits(max_extracted_chars=100))


def test_deadline_expires_and_names_what_timed_out():
    deadline = Deadline(-1.0)  # already over budget
    with pytest.raises(ExtractionTimeout, match="PDF page 7"):
        deadline.check("PDF page 7")


def test_deadline_does_not_fire_early():
    deadline = Deadline(30.0)
    deadline.check("parsing")
    assert deadline.remaining > 0
    assert not deadline.expired


def test_parse_limits_read_from_settings():
    limits = ParseLimits()
    assert limits.timeout_seconds > 0
    assert limits.max_archive_entries > 0
    assert isinstance(limits.deadline(), Deadline)
