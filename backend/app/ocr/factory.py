from functools import lru_cache

from app.core.config import settings
from app.ocr.base import OcrProvider


@lru_cache
def get_ocr_provider() -> OcrProvider:
    if settings.ocr_provider.lower() == "tesseract":
        from app.ocr.tesseract import TesseractOcrProvider

        return TesseractOcrProvider()
    from app.ocr.null import NullOcrProvider

    return NullOcrProvider()
