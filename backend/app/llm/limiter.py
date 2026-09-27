"""Shared, priority-aware scheduler for the Gemini quota (OCR, embeddings, chat).

Audit finding 7. The old token bucket held its lock while sleeping, so every caller
queued strictly FIFO: a chat call behind two OCR pages waited ~12 s at 10 RPM before
Gemini even saw it. This scheduler keeps the *same shared quota* (one start every
60/GEMINI_RPM seconds, process-wide) but:

* never sleeps while holding the lock (waiters park on a condition variable);
* serves interactive calls before background calls;
* stops background calls from taking the last ``GEMINI_INTERACTIVE_RESERVE`` slots of
  any rolling minute, so a chat request arriving mid-backlog finds a free slot;
* records wait time per call class, so queue wait can be measured in production.

The call class comes from a context variable. Request threads default to
``interactive``; the ingestion and workflow worker threads set ``background``.
Raise GEMINI_RPM only after confirming the account's real limit: separate buckets or a
higher local number just move the wait to Gemini 429s.
"""

from __future__ import annotations

import contextlib
import contextvars
import heapq
import itertools
import threading
import time
from collections import deque
from dataclasses import dataclass

from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)

INTERACTIVE = "interactive"
BACKGROUND = "background"
_PRIORITY = {INTERACTIVE: 0, BACKGROUND: 1}

_call_class: contextvars.ContextVar[str] = contextvars.ContextVar("gemini_call_class", default=INTERACTIVE)


def current_call_class() -> str:
    return _call_class.get()


def set_thread_call_class(name: str) -> None:
    """Set the class for the current thread/context (worker loops call this once)."""
    _call_class.set(name if name in _PRIORITY else INTERACTIVE)


@contextlib.contextmanager
def gemini_call_class(name: str):
    token = _call_class.set(name if name in _PRIORITY else INTERACTIVE)
    try:
        yield
    finally:
        _call_class.reset(token)


@dataclass
class _ClassStats:
    count: int = 0
    total_wait: float = 0.0
    max_wait: float = 0.0
    last_wait: float = 0.0

    def record(self, wait: float) -> None:
        self.count += 1
        self.total_wait += wait
        self.max_wait = max(self.max_wait, wait)
        self.last_wait = wait

    def as_dict(self) -> dict:
        return {
            "count": self.count,
            "avg_wait_ms": round(1000 * self.total_wait / self.count, 1) if self.count else 0.0,
            "max_wait_ms": round(1000 * self.max_wait, 1),
            "last_wait_ms": round(1000 * self.last_wait, 1),
        }


class TokenBucket:
    """Priority scheduler over one shared rate. Name kept for compatibility."""

    def __init__(self, rate_per_minute: float = 10.0, interactive_reserve: int = 0) -> None:
        self._rpm = max(float(rate_per_minute), 0.1)
        self._min_interval = 60.0 / self._rpm
        slots = int(self._rpm)
        self._reserve = max(0, min(int(interactive_reserve), slots - 1)) if slots >= 2 else 0
        self._cond = threading.Condition()
        self._last = float("-inf")
        self._recent: deque[float] = deque()
        self._waiting: list[tuple[int, int]] = []
        self._seq = itertools.count()
        self._stats = {INTERACTIVE: _ClassStats(), BACKGROUND: _ClassStats()}

    @property
    def queued(self) -> int:
        return len(self._waiting)

    @property
    def rate_per_minute(self) -> float:
        return self._rpm

    @property
    def interactive_reserve(self) -> int:
        return self._reserve

    def _trim(self, now: float) -> None:
        while self._recent and now - self._recent[0] >= 60.0:
            self._recent.popleft()

    def _reserve_wait(self, now: float) -> float:
        """Seconds a background call must wait so the interactive reserve stays free."""
        if self._reserve <= 0:
            return 0.0
        self._trim(now)
        allowed = int(self._rpm) - self._reserve
        if len(self._recent) < allowed:
            return 0.0
        # Wait until enough old starts leave the window.
        oldest_blocking = self._recent[len(self._recent) - allowed]
        return max(0.05, 60.0 - (now - oldest_blocking))

    def acquire(self, call_class: str | None = None) -> float:
        """Block until this call may start. Returns seconds waited."""
        cls = call_class or current_call_class()
        if cls not in _PRIORITY:
            cls = INTERACTIVE
        entry = (_PRIORITY[cls], next(self._seq))
        started = time.monotonic()
        with self._cond:
            heapq.heappush(self._waiting, entry)
            self._cond.notify_all()  # a higher-priority arrival may change the head
            try:
                while True:
                    now = time.monotonic()
                    if self._waiting and self._waiting[0] == entry:
                        wait = self._min_interval - (now - self._last)
                        if wait <= 0 and cls == BACKGROUND:
                            wait = self._reserve_wait(now)
                        if wait <= 0:
                            heapq.heappop(self._waiting)
                            self._last = now
                            self._recent.append(now)
                            self._trim(now)
                            break
                        self._cond.wait(timeout=wait)
                    else:
                        self._cond.wait(timeout=self._min_interval)
            except BaseException:
                if entry in self._waiting:
                    self._waiting.remove(entry)
                    heapq.heapify(self._waiting)
                raise
            finally:
                self._cond.notify_all()
            waited = time.monotonic() - started
            self._stats[cls].record(waited)
        return waited

    def stats(self) -> dict:
        with self._cond:
            return {
                "rpm": self._rpm,
                "interactive_reserve": self._reserve,
                "queued": len(self._waiting),
                "queued_by_class": {
                    INTERACTIVE: sum(1 for p, _ in self._waiting if p == _PRIORITY[INTERACTIVE]),
                    BACKGROUND: sum(1 for p, _ in self._waiting if p == _PRIORITY[BACKGROUND]),
                },
                "by_class": {name: s.as_dict() for name, s in self._stats.items()},
            }


def _configured() -> tuple[float, int]:
    rpm = float(getattr(settings, "gemini_rpm", 10) or 10)
    reserve = int(getattr(settings, "gemini_interactive_reserve", 0) or 0)
    return rpm, reserve


_rpm0, _reserve0 = _configured()
_gemini_bucket = TokenBucket(rate_per_minute=_rpm0, interactive_reserve=_reserve0)
_bucket_lock = threading.Lock()


def gemini_bucket() -> TokenBucket:
    global _gemini_bucket
    rpm, reserve = _configured()
    with _bucket_lock:
        current = _gemini_bucket
        expected_reserve = TokenBucket(rpm, reserve).interactive_reserve
        if abs(current.rate_per_minute - max(rpm, 0.1)) > 0.01 or current.interactive_reserve != expected_reserve:
            _gemini_bucket = TokenBucket(rate_per_minute=rpm, interactive_reserve=reserve)
        return _gemini_bucket


def acquire_gemini(call_class: str | None = None) -> float:
    bucket = gemini_bucket()
    cls = call_class or current_call_class()
    waited = bucket.acquire(cls)
    if waited >= 1.0:
        logger.info("gemini quota wait %.2fs class=%s queued=%d", waited, cls, bucket.queued)
    return waited


def gemini_stats() -> dict:
    return gemini_bucket().stats()
