from app.ocr.base import OcrProvider


class FakeOcrProvider(OcrProvider):
    """Deterministic OCR for tests. Never calls the network."""

    name = "fake"

    def __init__(self, text: str = "Recovered text from a scanned page.") -> None:
        self._text = text

    @property
    def available(self) -> bool:
        return True

    def image_to_text(self, image_bytes: bytes) -> str:
        if not image_bytes:
            return ""
        return self._text
