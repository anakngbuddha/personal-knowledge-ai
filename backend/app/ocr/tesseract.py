import io

from app.core.config import settings
from app.core.logging import get_logger
from app.ocr.base import OcrProvider

logger = get_logger(__name__)


class TesseractOcrProvider(OcrProvider):
    """pytesseract + Pillow. Optional import: the API starts fine without either."""

    name = "tesseract"

    def __init__(self, language: str | None = None) -> None:
        self._language = language or settings.ocr_language
        self._ready: bool | None = None

    @property
    def available(self) -> bool:
        if self._ready is None:
            try:
                import pytesseract  # noqa: F401
                from PIL import Image  # noqa: F401

                import pytesseract as pt

                pt.get_tesseract_version()
                self._ready = True
            except Exception as exc:  # noqa: BLE001 - a missing binary is the normal case
                logger.warning("tesseract OCR unavailable: %s", exc)
                self._ready = False
        return self._ready

    def image_to_text(self, image_bytes: bytes) -> str:
        if not self.available:
            return ""
        import pytesseract
        from PIL import Image

        with Image.open(io.BytesIO(image_bytes)) as image:
            if image.mode not in ("L", "RGB"):
                image = image.convert("RGB")
            return pytesseract.image_to_string(image, lang=self._language) or ""
