"""Citation anchors.

A citation is only trustworthy if it resolves to one place in the source, so the
anchor is captured during extraction and carried through chunking untouched. Each
format contributes the anchor it actually has:

| format | anchor                                  |
|--------|-----------------------------------------|
| pdf    | page number                             |
| pptx   | slide number (+ slide title)            |
| xlsx   | sheet name + cell range                 |
| docx   | heading path                            |
| md/txt | heading path                            |
| html   | heading path                            |
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class Anchor:
    page_number: int | None = None
    slide_number: int | None = None
    sheet_name: str | None = None
    cell_range: str | None = None
    section_title: str | None = None
    heading_path: tuple[str, ...] = field(default_factory=tuple)

    def key(self) -> tuple:
        """Grouping key for chunking: a chunk never spans two anchors."""
        return (
            self.page_number,
            self.slide_number,
            self.sheet_name,
            self.cell_range,
            self.section_title,
            self.heading_path,
        )

    def label(self) -> str:
        """Human-readable citation suffix, e.g. 'p. 12' or 'Pricing!A1:D20'."""
        if self.page_number is not None:
            base = f"p. {self.page_number}"
        elif self.slide_number is not None:
            base = f"slide {self.slide_number}"
        elif self.sheet_name:
            base = f"{self.sheet_name}!{self.cell_range}" if self.cell_range else self.sheet_name
        elif self.heading_path:
            return " > ".join(self.heading_path)
        elif self.section_title:
            return self.section_title
        else:
            return ""
        if self.section_title and self.section_title not in base:
            return f"{base} - {self.section_title}"
        return base

    def as_dict(self) -> dict:
        return {
            "page_number": self.page_number,
            "slide_number": self.slide_number,
            "sheet_name": self.sheet_name,
            "cell_range": self.cell_range,
            "section_title": self.section_title,
            "heading_path": list(self.heading_path),
            "label": self.label(),
        }
