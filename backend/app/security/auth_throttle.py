"""In-process throttling for unauthenticated auth endpoints.

The login, signup and SSO-start routes have no principal to rate-limit on, so they
are limited per client IP, and failed logins are additionally counted per account.
Counters are sliding windows kept in memory: they are per process, which matches the
single-web-process Render deployment. Run several workers and each one enforces the
limit on its own share of traffic, so put a shared limiter (gateway or Redis) in
front before scaling out.
"""

from __future__ import annotations

import math
import threading
import time
from collections import deque

from fastapi import HTTPException, Request

from app.core.config import settings

_MAX_KEYS = 50_000


class SlidingWindowCounter:
    """Timestamps of recent events per key, bounded in total key count."""

    def __init__(self, max_keys: int = _MAX_KEYS) -> None:
        self._events: dict[str, deque[float]] = {}
        self._lock = threading.Lock()
        self._max_keys = max_keys

    def _prune(self, events: deque[float], cutoff: float) -> None:
        while events and events[0] <= cutoff:
            events.popleft()

    def _make_room(self, now: float, window: float) -> None:
        if len(self._events) < self._max_keys:
            return
        cutoff = now - window
        for key in [k for k, v in self._events.items() if not v or v[-1] <= cutoff]:
            self._events.pop(key, None)
        # Still full: forget the oldest keys rather than grow without bound.
        while len(self._events) >= self._max_keys:
            self._events.pop(next(iter(self._events)))

    def add(self, key: str, window: float, now: float | None = None) -> int:
        now = time.monotonic() if now is None else now
        with self._lock:
            events = self._events.get(key)
            if events is None:
                self._make_room(now, window)
                events = self._events[key] = deque()
            self._prune(events, now - window)
            events.append(now)
            return len(events)

    def count(self, key: str, window: float, now: float | None = None) -> int:
        now = time.monotonic() if now is None else now
        with self._lock:
            events = self._events.get(key)
            if not events:
                return 0
            self._prune(events, now - window)
            return len(events)

    def retry_after(self, key: str, window: float, now: float | None = None) -> int:
        now = time.monotonic() if now is None else now
        with self._lock:
            events = self._events.get(key)
            if not events:
                return 1
            return max(1, math.ceil(events[0] + window - now))

    def clear(self, key: str) -> None:
        with self._lock:
            self._events.pop(key, None)

    def reset(self) -> None:
        with self._lock:
            self._events.clear()


_counter = SlidingWindowCounter()


def enabled() -> bool:
    return bool(settings.auth_rate_limit_enabled)


def client_ip(request: Request) -> str:
    """Client address, trusting X-Forwarded-For only for the configured proxy hops.

    Each trusted proxy appends the address it saw, so with N hops the real client is
    the N-th entry from the right. Anything further left is client-controlled.
    """
    hops = max(0, int(settings.trusted_proxy_hops))
    if hops:
        forwarded = [p.strip() for p in request.headers.get("x-forwarded-for", "").split(",") if p.strip()]
        if len(forwarded) >= hops:
            return forwarded[-hops][:64]
    return (request.client.host if request.client else "unknown")[:64]


def _too_many(retry: int) -> HTTPException:
    return HTTPException(429, "too many attempts; try again later", headers={"Retry-After": str(retry)})


def enforce(bucket: str, key: str, limit: int, window: float) -> None:
    """Count one attempt and raise 429 once more than `limit` happen within `window`."""
    if not enabled() or limit <= 0:
        return
    full = f"{bucket}:{key}"
    if _counter.add(full, window) > limit:
        raise _too_many(_counter.retry_after(full, window))


def blocked(bucket: str, key: str, limit: int, window: float) -> int | None:
    """Retry-After seconds if `key` already reached `limit` events, else None."""
    if not enabled() or limit <= 0:
        return None
    full = f"{bucket}:{key}"
    if _counter.count(full, window) >= limit:
        return _counter.retry_after(full, window)
    return None


def record(bucket: str, key: str, window: float) -> int:
    """Record an event without enforcing; returns the count inside the window."""
    return _counter.add(f"{bucket}:{key}", window)


def clear(bucket: str, key: str) -> None:
    _counter.clear(f"{bucket}:{key}")


def reset_all() -> None:
    """Test helper."""
    _counter.reset()


def raise_blocked(retry: int) -> None:
    raise _too_many(retry)
