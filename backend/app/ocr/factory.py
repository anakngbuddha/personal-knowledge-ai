from functools import lru_cache

from app.core.config import settings
from app.ocr.base import OcrProvider


@lru_cache
def get_ocr_provider() -> OcrProvider:
    provider_name = (settings.ocr_provider or "none").lower().strip()
    if provider_name == "gemini":
        from app.ocr.gemini import GeminiOcrProvider
        return GeminiOcrProvider()
    if provider_name == "tesseract":
        from app.ocr.tesseract import TesseractOcrProvider
        return TesseractOcrProvider()
    from app.ocr.null import NullOcrProvider
    return NullOcrProvider()
