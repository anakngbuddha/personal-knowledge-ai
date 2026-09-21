"""Gemini vision OCR for scanned PDFs.

Uses httpx (same as the chat/embedding providers) so Render does not need the
Google SDK or any native binary. Calls go through the shared Gemini token bucket.
"""

from __future__ import annotations

import base64
import logging

import httpx

from app.core.config import settings
from app.core.errors import ProviderRateLimited
from app.llm.limiter import acquire_gemini
from app.ocr.base import OcrProvider

logger = logging.getLogger(__name__)

_EXTRACT_PROMPT = (
    "Extract all visible text from this page image. Return only the text content, "
    "preserving structure like headings, lists, and tables."
)


class GeminiOcrProvider(OcrProvider):
    name = "gemini"

    def __init__(self) -> None:
        self._api_key = settings.gemini_api_key
        self._model = settings.gemini_generation_model
        self._timeout = 60.0

    @property
    def available(self) -> bool:
        return bool(self._api_key)

    def image_to_text(self, image_bytes: bytes) -> str:
        if not image_bytes or not self._api_key:
            return ""
        acquire_gemini()
        payload = {
            "contents": [
                {
                    "parts": [
                        {"text": _EXTRACT_PROMPT},
                        {
                            "inline_data": {
                                "mime_type": "image/png",
                                "data": base64.b64encode(image_bytes).decode("ascii"),
                            }
                        },
                    ]
                }
            ]
        }
        url = f"{settings.gemini_api_base}/models/{self._model}:generateContent"
        try:
            response = httpx.post(
                url,
                params={"key": self._api_key},
                json=payload,
                timeout=self._timeout,
            )
        except httpx.TransportError as exc:
            logger.warning("Gemini OCR transport error: %s", exc)
            return ""
        if response.status_code == 429:
            raise ProviderRateLimited("Gemini OCR rate limit reached")
        if response.status_code >= 400:
            logger.warning("Gemini OCR HTTP %s: %s", response.status_code, response.text[:300])
            return ""
        data = response.json()
        try:
            parts = data["candidates"][0]["content"]["parts"]
            return "".join(str(part.get("text") or "") for part in parts).strip()
        except (KeyError, IndexError, TypeError):
            logger.warning("Gemini OCR returned no text")
            return ""
