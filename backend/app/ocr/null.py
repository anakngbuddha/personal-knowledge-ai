from app.ocr.base import OcrProvider


class NullOcrProvider(OcrProvider):
    """The default. OCR is off unless someone deliberately turns it on.

    Reasoning recorded so it does not look like an oversight: Tesseract is a native
    binary, the corpus in Project_Plan.md is ~50 documents with a single owner, and a
    scanned PDF is better fixed at the source than silently OCR'd at 80% accuracy
    into collateral that answers will later cite. When a scanned PDF does arrive, the
    document fails with a message that says exactly that, rather than succeeding with
    zero chunks.
    """

    name = "none"

    @property
    def available(self) -> bool:
        return False

    def image_to_text(self, image_bytes: bytes) -> str:
        return ""
