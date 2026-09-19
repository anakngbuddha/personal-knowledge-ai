import pytest

from app.core.errors import UnsupportedFileType
from app.documents.extraction import detect_file_type, extract


def test_detect_file_type():
    assert detect_file_type("Lecture 03.PDF") == "pdf"
    assert detect_file_type("notes.txt") == "txt"
    assert detect_file_type("paper.docx") == "docx"
    with pytest.raises(UnsupportedFileType):
        detect_file_type("image.png")


def test_txt_headings_become_sections(tmp_path):
    path = tmp_path / "notes.txt"
    path.write_text("# Laplace Transform\nDefinition of the transform.\n\n# Inverse\nInverse rules.\n")
    result = extract(path, "txt")
    sections = [block.section_title for block in result.blocks]
    assert sections == ["Laplace Transform", "Inverse"]
