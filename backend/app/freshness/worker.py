"""Background poller for vendor collateral freshness checks."""

from __future__ import annotations

import os
import socket
import threading
import time
from datetime import timedelta

from app.core.config import settings
from app.core.logging import get_logger
from app.db.session import SessionLocal
from app.freshness.scraper import CheckResult, _now, claim_due_source

logger = get_logger(__name__)

_stop = threading.Event()
_threads: list[threading.Thread] = []


def worker_id(index: int = 0) -> str:
    return f"freshness:{socket.gethostname()}:{os.getpid()}:{index}"


def run_once(identity: str, fetcher=None) -> CheckResult | None:
    """Claim a due source and queue its crawl. The fetch runs on the ingestion worker."""
    del fetcher  # crawls use the SSRF fetcher inside the queued job
    from app.jobs.queue import enqueue_freshness_crawl

    db = SessionLocal()
    try:
        source = claim_due_source(db, identity)
        if source is None:
            return None
        logger.info("freshness: queueing crawl %s (%s)", source.id, source.url)
        source.next_check_at = _now() + timedelta(seconds=source.check_interval_seconds)
        source.locked_by = None
        source.locked_at = None
        enqueue_freshness_crawl(db, vendor_source_id=source.id, org_id=source.org_id)
        return CheckResult(
            source_id=source.id,
            status="queued",
            hash=source.last_hash,
            changed=False,
            alert_id=None,
        )
    except Exception:  # noqa: BLE001 - loop must survive a single source
        logger.exception("freshness worker %s: unexpected error", identity)
        return None
    finally:
        db.close()


def loop(index: int = 0) -> None:
    identity = worker_id(index)
    logger.info("freshness worker %s started", identity)
    while not _stop.is_set():
        result = run_once(identity)
        if result is None:
            _stop.wait(settings.freshness_poll_seconds)
    logger.info("freshness worker %s stopped", identity)


def start_freshness_workers() -> None:
    if not settings.freshness_worker_enabled:
        logger.warning("freshness worker disabled (FRESHNESS_WORKER_ENABLED=false)")
        return
    if _threads:
        return
    thread = threading.Thread(target=loop, args=(0,), daemon=True, name="freshness-0")
    thread.start()
    _threads.append(thread)


def stop_freshness_workers(timeout: float = 5.0) -> None:
    _stop.set()
    deadline = time.monotonic() + timeout
    for thread in _threads:
        thread.join(max(0.0, deadline - time.monotonic()))
    _threads.clear()
    _stop.clear()
