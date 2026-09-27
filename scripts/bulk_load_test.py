"""Bulk ingestion test at 10x the real corpus.

    cd backend && EMBEDDING_PROVIDER=fake STORAGE_BACKEND=local \
        python ../scripts/bulk_load_test.py --count 500

Phase 1 exit criterion: "Bulk test at 10x the real corpus (500 documents): the queue
drains, memory is flat, statuses correct." This script generates synthetic collateral,
queues it, drains the queue with the real worker, and reports peak RSS so "memory is
flat" is a number rather than a feeling.
"""

import argparse
import os
import resource
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from sqlalchemy import func, select  # noqa: E402

from app.db.models import Document, DocumentStatus, IngestionJob, JobStatus  # noqa: E402
from app.db.session import system_session  # noqa: E402
from app.documents.metadata import DocumentMetadataIn  # noqa: E402
from app.documents.service import create_document, enqueue_ingestion  # noqa: E402
from app.jobs import worker  # noqa: E402
from app.security.deps import get_or_create_default_org  # noqa: E402
from app.security.principal import owner_principal  # noqa: E402

PRODUCTS = ["OrbitCloud", "VaultStore", "MeetBridge", "LegacyEdge", "SentryID"]
CAPABILITIES = [
    "identity federation",
    "site-to-site VPN",
    "call recording",
    "object replication",
    "single sign-on",
]


def synthetic_markdown(index: int) -> bytes:
    product = PRODUCTS[index % len(PRODUCTS)]
    capability = CAPABILITIES[index % len(CAPABILITIES)]
    body = "\n\n".join(
        f"Paragraph {n} about {product} and {capability}. "
        + " ".join(f"detail{n}-{w}" for w in range(40))
        for n in range(12)
    )
    return f"# {product} datasheet {index}\n\n## Capabilities\n\n{capability}\n\n{body}\n".encode()


def rss_mb() -> float:
    usage = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    # Linux reports KiB, macOS reports bytes.
    return usage / 1024 if sys.platform != "darwin" else usage / (1024 * 1024)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--count", type=int, default=500)
    parser.add_argument("--timeout", type=int, default=1800)
    args = parser.parse_args()

    if os.environ.get("EMBEDDING_PROVIDER", "").lower() != "fake":
        print(
            "WARNING: not using EMBEDDING_PROVIDER=fake. "
            f"This will make {args.count} real embedding calls.",
            file=sys.stderr,
        )

    started = time.monotonic()
    db = system_session()
    created = 0
    try:
        principal = owner_principal(get_or_create_default_org(db).id)
        for index in range(args.count):
            document = create_document(
                db,
                principal=principal,
                original_filename=f"synthetic-{index:04d}.md",
                data=synthetic_markdown(index),
                mime_type="text/markdown",
                metadata=DocumentMetadataIn(
                    vendor="SyntheticCorp",
                    ownership="own",
                    products_referenced=[PRODUCTS[index % len(PRODUCTS)]],
                    valid_until="2030-01-01",
                ),
            )
            enqueue_ingestion(db, document)
            created += 1
            if created % 50 == 0:
                print(f"queued {created}/{args.count}  rss={rss_mb():.0f} MB")
    finally:
        db.close()
    queued_at = time.monotonic()
    print(f"queued {created} documents in {queued_at - started:.1f}s  rss={rss_mb():.0f} MB")

    identity = worker.worker_id(0)
    drained = 0
    while time.monotonic() - queued_at < args.timeout:
        if not worker.run_once(identity):
            break
        drained += 1
        if drained % 50 == 0:
            print(f"processed {drained}  rss={rss_mb():.0f} MB")

    db = system_session()
    try:
        doc_counts = dict(
            db.execute(select(Document.status, func.count()).group_by(Document.status)).all()
        )
        job_counts = dict(
            db.execute(
                select(IngestionJob.status, func.count()).group_by(IngestionJob.status)
            ).all()
        )
    finally:
        db.close()

    elapsed = time.monotonic() - started
    print("\n--- results")
    print(f"elapsed          : {elapsed:.1f}s")
    print(f"jobs processed   : {drained}")
    print(f"document statuses: {doc_counts}")
    print(f"job statuses     : {job_counts}")
    print(f"peak rss         : {rss_mb():.0f} MB")

    ready = doc_counts.get(DocumentStatus.READY, 0)
    dead = job_counts.get(JobStatus.DEAD, 0)
    queued_left = job_counts.get(JobStatus.QUEUED, 0) + job_counts.get(JobStatus.FAILED, 0)
    ok = queued_left == 0 and dead == 0 and ready >= created
    print(f"\n{'PASS' if ok else 'FAIL'}: queue drained={queued_left == 0} dead={dead} ready={ready}")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
