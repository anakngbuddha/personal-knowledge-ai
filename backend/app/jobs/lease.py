"""Renew a queue lease while a job runs (audit finding 13).

SKIP LOCKED only protects simultaneous claims. Once a job is RUNNING, the only thing
that stops a second worker from reclaiming it is a fresh lease timestamp. This keeper
renews it on a daemon thread, with its own DB session, until the job finishes.
"""

from __future__ import annotations

import threading
from collections.abc import Callable

from app.core.logging import get_logger

logger = get_logger(__name__)


class LeaseKeeper:
    def __init__(self, renew: Callable[[], bool], *, interval: float, name: str = "lease") -> None:
        self._renew = renew
        self._interval = max(0.05, float(interval))
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._run, daemon=True, name=name)
        self.lost = False
        self.renewals = 0

    def _run(self) -> None:
        while not self._stop.wait(self._interval):
            try:
                if self._renew():
                    self.renewals += 1
                else:
                    self.lost = True
                    logger.warning("%s: lease lost (job reclaimed or finished elsewhere)", self._thread.name)
                    return
            except Exception:  # noqa: BLE001 - a failed renewal is retried next tick
                logger.exception("%s: lease renewal failed", self._thread.name)

    def __enter__(self) -> "LeaseKeeper":
        self._thread.start()
        return self

    def __exit__(self, *exc) -> None:
        self._stop.set()
        self._thread.join(timeout=self._interval + 1.0)
