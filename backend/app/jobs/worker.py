"""The single ingestion worker.

Runs either inside the API process (a daemon thread, good enough for one owner and
50 documents) or standalone via `python scripts/worker.py`. Same loop either way, so
moving it out of the web process later is a deployment change, not a code change.
"""

from __future__ import annotations

import os
import socket
import threading
import time

from app.core.config import settings
from app.core.errors import (
    ExtractionError,
    ExtractionTimeout,
    MalwareDetected,
    UnsafeFile,
    UnsupportedFileType,
)
from app.core.logging import get_logger
from app.db.session import SessionLocal
from app.jobs import queue

logger = get_logger(__name__)

# A bad file will never become a good file. Retrying it just burns the worker.
PERMANENT_FAILURES = (
    UnsupportedFileType,
    UnsafeFile,
    MalwareDetected,
    ExtractionError,
    ExtractionTimeout,
)

_stop = threading.Event()
_threads: list[threading.Thread] = []


def worker_id(index: int = 0) -> str:
    return f"{socket.gethostname()}:{os.getpid()}:{index}"


def run_once(identity: str) -> bool:
    """Claim and run at most one job. Returns True if work was done."""
    from app.documents.service import process_document

    db = SessionLocal()
    try:
        job = queue.claim(db, identity)
        if job is None:
            return False
        document_id = job.document_id
        logger.info("job %s: ingesting document %s (attempt %s)", job.id, document_id, job.attempts)
        try:
            process_document(document_id)
        except PERMANENT_FAILURES as exc:
            queue.fail(db, job, f"{type(exc).__name__}: {exc}", retryable=False)
            return True
        except Exception as exc:  # noqa: BLE001 - transient by assumption, retried
            queue.fail(db, job, f"{type(exc).__name__}: {exc}", retryable=True)
            return True
        queue.succeed(db, job)
        return True
    finally:
        db.close()


def loop(index: int = 0) -> None:
    identity = worker_id(index)
    logger.info("ingestion worker %s started", identity)
    while not _stop.is_set():
        try:
            did_work = run_once(identity)
        except Exception:  # noqa: BLE001 - the loop must outlive any single failure
            logger.exception("worker %s: unexpected error", identity)
            did_work = False
        if not did_work:
            _stop.wait(settings.worker_poll_seconds)
    logger.info("ingestion worker %s stopped", identity)


def start_background_workers() -> None:
    if not settings.worker_enabled:
        logger.warning("in-process ingestion worker disabled (WORKER_ENABLED=false)")
        return
    if _threads:
        return
    for index in range(max(1, settings.worker_concurrency)):
        thread = threading.Thread(target=loop, args=(index,), daemon=True, name=f"ingest-{index}")
        thread.start()
        _threads.append(thread)


def stop_background_workers(timeout: float = 5.0) -> None:
    _stop.set()
    deadline = time.monotonic() + timeout
    for thread in _threads:
        thread.join(max(0.0, deadline - time.monotonic()))
    _threads.clear()
    _stop.clear()
