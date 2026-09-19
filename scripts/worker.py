"""Run the ingestion worker as its own process.

    cd backend && python ../scripts/worker.py

Use this when you would rather not have ingestion share the web dyno. Set
WORKER_ENABLED=false on the API process so only one of them drains the queue.
"""

import signal
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from app.core.logging import get_logger, setup_logging  # noqa: E402
from app.jobs import worker  # noqa: E402

logger = get_logger("worker")


def main() -> None:
    setup_logging()

    def shutdown(signum, _frame):
        logger.info("received signal %s, stopping", signum)
        worker._stop.set()  # noqa: SLF001 - this is the process-level stop switch

    signal.signal(signal.SIGINT, shutdown)
    signal.signal(signal.SIGTERM, shutdown)
    worker.loop()


if __name__ == "__main__":
    main()
