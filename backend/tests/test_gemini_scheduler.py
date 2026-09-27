"""Priority-aware Gemini scheduler (audit finding 7)."""

from __future__ import annotations

import threading
import time

from app.llm.limiter import BACKGROUND, INTERACTIVE, TokenBucket, current_call_class, gemini_call_class


def test_same_class_calls_keep_the_shared_spacing():
    bucket = TokenBucket(rate_per_minute=600)  # 0.1 s between starts
    started = time.monotonic()
    for _ in range(3):
        bucket.acquire(INTERACTIVE)
    assert time.monotonic() - started >= 0.18


def test_interactive_call_overtakes_queued_background_work():
    bucket = TokenBucket(rate_per_minute=120)  # 0.5 s between starts
    bucket.acquire(BACKGROUND)
    order: list[str] = []

    def run(cls: str) -> None:
        bucket.acquire(cls)
        order.append(cls)

    background = threading.Thread(target=run, args=(BACKGROUND,))
    background.start()
    time.sleep(0.1)
    interactive = threading.Thread(target=run, args=(INTERACTIVE,))
    interactive.start()
    interactive.join(3)
    background.join(3)
    assert order == [INTERACTIVE, BACKGROUND]


def test_lock_is_not_held_while_waiting():
    bucket = TokenBucket(rate_per_minute=60)
    bucket.acquire(BACKGROUND)
    waiter = threading.Thread(target=bucket.acquire, args=(BACKGROUND,), daemon=True)
    waiter.start()
    time.sleep(0.05)
    started = time.monotonic()
    stats = bucket.stats()  # needs the lock; must not wait ~1 s for the sleeper
    assert time.monotonic() - started < 0.2
    assert stats["queued"] == 1


def test_background_cannot_take_the_interactive_reserve():
    bucket = TokenBucket(rate_per_minute=60, interactive_reserve=2)
    now = time.monotonic()
    bucket._recent.extend(now - 1.0 for _ in range(58))
    assert bucket._reserve_wait(now) > 0
    bucket._recent.clear()
    bucket._recent.extend(now - 1.0 for _ in range(57))
    assert bucket._reserve_wait(now) == 0


def test_wait_is_recorded_per_class():
    bucket = TokenBucket(rate_per_minute=600)
    bucket.acquire(INTERACTIVE)
    bucket.acquire(BACKGROUND)
    by_class = bucket.stats()["by_class"]
    assert by_class[INTERACTIVE]["count"] == 1
    assert by_class[BACKGROUND]["count"] == 1
    assert by_class[BACKGROUND]["max_wait_ms"] >= 50


def test_call_class_context_manager():
    assert current_call_class() == INTERACTIVE
    with gemini_call_class(BACKGROUND):
        assert current_call_class() == BACKGROUND
    assert current_call_class() == INTERACTIVE
