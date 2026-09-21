"""Gemini vision OCR provider for scanned PDFs.

Scanned PDFs are rasterized page-by-page and sent to Gemini's multimodal API.
Rate limiting respects the free-tier limit (~10 req/min).
"""

from __future__ import annotations

import io
import logging
import time
from threading import Lock

import google.generativeai as genai

from app.core.config import settings
from app.core.errors import ExtractionError
from app.ocr.base import OcrProvider

logger = logging.getLogger(__name__)


class GeminiOcrProvider(OcrProvider):
    """Use Gemini vision API to extract text from image-based PDFs."""

    name = "gemini"
    _rate_limiter_lock = Lock()
    _last_call_time = 0
    _min_interval = 6.0

    def __init__(self):
        if not settings.gemini_api_key:
            raise ExtractionError("Gemini API key not configured")
        genai.configure(api_key=settings.gemini_api_key)
        self._model = genai.GenerativeModel("gemini-2.0-flash")

    @property
    def available(self) -> bool:
        return bool(settings.gemini_api_key)

    def image_to_text(self, image_bytes: bytes) -> str:
        try:
            self._wait_for_rate_limit()
            response = self._model.generate_content([
                "Extract all visible text from this page image. Return only the text content, preserving structure like headings, lists, and tables.",
                {"mime_type": "image/png", "data": image_bytes},
            ])
            return response.text or ""
        except Exception as exc:
            logger.warning("Gemini OCR failed: %s", exc)
            return ""

    def _wait_for_rate_limit(self) -> None:
        with self._rate_limiter_lock:
            elapsed = time.time() - GeminiOcrProvider._last_call_time
            if elapsed < self._min_interval:
                time.sleep(self._min_interval - elapsed)
            GeminiOcrProvider._last_call_time = time.time()
