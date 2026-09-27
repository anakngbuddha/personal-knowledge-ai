"""Runtime contention metrics for the single Render web process (audit finding 8).

The web process also hosts the ingestion, workflow and freshness threads. They do not
block the event loop (/ask is sync and runs in Starlette's thread pool), but they do
compete for CPU, the DB pool and the Gemini quota. This module measures each of those
so a separate worker service is justified by numbers, not guessed:

* event-loop lag: drift of a 0.5 s asyncio sleep;
* thread-pool saturation: anyio's default limiter (borrowed / total, tasks waiting);
* DB pool: checked-out connections and overflow in use;
* Gemini: queue depth and wait by call class (see app.llm.limiter).
"""

from __future__ import annotations

import asyncio
import time

from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)

_state: dict[str, float] = {"lag_ms": 0.0, "lag_max_ms": 0.0, "samples": 0}
_task: asyncio.Task | None = None


def _thread_pool() -> dict | None:
    try:
        from anyio import to_thread

        limiter = to_thread.current_default_thread_limiter()
        stats = limiter.statistics()
        return {
            "total": limiter.total_tokens,
            "borrowed": stats.borrowed_tokens,
            "waiting": stats.tasks_waiting,
        }
    except Exception:  # noqa: BLE001 - only available inside the event loop
        return None


def _db_pool() -> dict | None:
    try:
        from app.db.session import engine

        pool = engine.pool
        return {
            "size": pool.size(),
            "checked_out": pool.checkedout(),
            "overflow": pool.overflow(),
        }
    except Exception:  # noqa: BLE001 - SQLite/StaticPool has no size()
        return None


def snapshot() -> dict:
    from app.llm.limiter import gemini_stats

    return {
        "event_loop": {
            "lag_ms": round(_state["lag_ms"], 1),
            "lag_max_ms": round(_state["lag_max_ms"], 1),
            "samples": int(_state["samples"]),
        },
        "thread_pool": _thread_pool(),
        "db_pool": _db_pool(),
        "gemini": gemini_stats(),
        "in_process_workers": {
            "ingestion": bool(settings.worker_enabled),
            "workflow": bool(settings.workflow_worker_enabled),
            "freshness": bool(settings.freshness_worker_enabled),
        },
    }


async def _monitor(interval: float) -> None:
    loop = asyncio.get_running_loop()
    last_log = time.monotonic()
    while True:
        start = loop.time()
        await asyncio.sleep(0.5)
        lag = max(0.0, (loop.time() - start - 0.5) * 1000.0)
        _state["lag_ms"] = lag
        _state["lag_max_ms"] = max(_state["lag_max_ms"], lag)
        _state["samples"] += 1
        if time.monotonic() - last_log >= interval:
            logger.info("runtime metrics %s", snapshot())
            _state["lag_max_ms"] = 0.0
            last_log = time.monotonic()


def start_runtime_metrics() -> None:
    global _task
    if not settings.runtime_metrics_enabled or _task is not None:
        return
    try:
        _task = asyncio.get_running_loop().create_task(
            _monitor(max(5.0, float(settings.runtime_metrics_interval_seconds)))
        )
    except RuntimeError:
        _task = None


async def stop_runtime_metrics() -> None:
    global _task
    if _task is None:
        return
    _task.cancel()
    try:
        await _task
    except (asyncio.CancelledError, Exception):  # noqa: BLE001
        pass
    _task = None
