"""Retry schedule. Pure arithmetic, kept separate so it can be tested without a DB."""

from __future__ import annotations

import hashlib


def backoff_seconds(
    attempt: int,
    *,
    base: float,
    maximum: float,
    jitter_key: str = "",
) -> float:
    """Exponential backoff with deterministic jitter.

    Jitter is derived from `jitter_key` (the job id) rather than `random`, so the
    schedule is reproducible in tests and in incident reconstruction. Spreading is
    what matters, not unpredictability.
    """
    if attempt < 1:
        raise ValueError("attempt is 1-based")
    delay = min(base * (2 ** (attempt - 1)), maximum)
    if not jitter_key:
        return delay
    digest = hashlib.sha256(f"{jitter_key}:{attempt}".encode()).digest()
    fraction = digest[0] / 255.0  # 0.0 .. 1.0
    # Full jitter on the top 25% of the window: keeps ordering roughly intact while
    # still preventing a thundering herd after an outage.
    return round(delay * (0.75 + 0.25 * fraction), 3)
