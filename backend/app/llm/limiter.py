"""Shared token-bucket limiter for Gemini free-tier calls (OCR, embeddings, chat)."""

from __future__ import annotations

import time
from threading import Lock

from app.core.config import settings


class TokenBucket:
    def __init__(self, rate_per_minute: float = 10.0) -> None:
        self._min_interval = 60.0 / max(rate_per_minute, 0.1)
        self._lock = Lock()
        self._last = 0.0
        self._queued = 0

    @property
    def queued(self) -> int:
        return self._queued

    def acquire(self) -> None:
        with self._lock:
            self._queued += 1
        try:
            with self._lock:
                elapsed = time.time() - self._last
                wait = self._min_interval - elapsed
                if wait > 0:
                    time.sleep(wait)
                self._last = time.time()
        finally:
            with self._lock:
                self._queued = max(0, self._queued - 1)


_gemini_bucket = TokenBucket(rate_per_minute=10.0)


def gemini_bucket() -> TokenBucket:
    global _gemini_bucket
    rpm = float(getattr(settings, "gemini_rpm", 10) or 10)
    if abs(_gemini_bucket._min_interval - 60.0 / max(rpm, 0.1)) > 0.01:
        _gemini_bucket = TokenBucket(rate_per_minute=rpm)
    return _gemini_bucket


def acquire_gemini() -> None:
    gemini_bucket().acquire()
