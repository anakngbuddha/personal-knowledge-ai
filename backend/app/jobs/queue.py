"""Durable ingestion queue on PostgreSQL.

Why a table instead of `BackgroundTasks`: the plan requires "background processing
with per-job status, retry with backoff, and a failed state". An in-process task list
loses every queued job when Render restarts the dyno, which makes per-job status a
fiction and retry impossible. A table costs one `SELECT ... FOR UPDATE SKIP LOCKED`
and buys durability, visibility, and safe concurrency.

Still a single worker. No Redis, no Celery, no distributed queue, exactly as the plan
specifies for this corpus size.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.logging import get_logger
from app.db.models import IngestionJob, JobStatus
from app.jobs.backoff import backoff_seconds

logger = get_logger(__name__)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def enqueue(
    db: Session,
    *,
    document_id: uuid.UUID,
    org_id: uuid.UUID | None,
    kind: str = "ingest",
    replace_existing: bool = True,
) -> IngestionJob:
    """Queue ingestion for a document.

    `replace_existing` collapses duplicate queued jobs for the same document, so
    hammering the retry button cannot fan out into N embeddings bills.
    """
    if replace_existing:
        db.execute(
            update(IngestionJob)
            .where(
                IngestionJob.document_id == document_id,
                IngestionJob.kind == kind,
                IngestionJob.status.in_([JobStatus.QUEUED, JobStatus.FAILED]),
            )
            .values(status=JobStatus.DEAD, error_message="superseded by a newer request")
        )

    job = IngestionJob(
        document_id=document_id,
        org_id=org_id,
        kind=kind,
        status=JobStatus.QUEUED,
        max_attempts=settings.job_max_attempts,
        run_after=_now(),
    )
    db.add(job)
    db.commit()
    db.refresh(job)
    return job


def enqueue_freshness_crawl(
    db: Session,
    *,
    vendor_source_id: uuid.UUID,
    org_id: uuid.UUID | None,
) -> IngestionJob:
    """Queue a site crawl. A source already running or waiting is not duplicated."""
    pending = list(
        db.scalars(
            select(IngestionJob).where(
                IngestionJob.kind == "freshness_crawl",
                IngestionJob.org_id == org_id,
                IngestionJob.status.in_([JobStatus.QUEUED, JobStatus.FAILED, JobStatus.RUNNING]),
            )
        )
    )
    running: IngestionJob | None = None
    for row in pending:
        if str((row.payload or {}).get("vendor_source_id")) != str(vendor_source_id):
            continue
        if row.status == JobStatus.RUNNING:
            running = row
            continue
        row.status = JobStatus.DEAD
        row.error_message = "superseded by a newer request"
    if running is not None:
        db.commit()
        return running

    job = IngestionJob(
        document_id=None,
        org_id=org_id,
        kind="freshness_crawl",
        status=JobStatus.QUEUED,
        max_attempts=settings.job_max_attempts,
        run_after=_now(),
        payload={"vendor_source_id": str(vendor_source_id)},
    )
    db.add(job)
    db.commit()
    db.refresh(job)
    return job


def claim(db: Session, worker_id: str) -> IngestionJob | None:
    """Atomically claim the next runnable job. Safe to run from several workers."""
    reap_stale(db)
    job = db.scalars(
        select(IngestionJob)
        .where(
            IngestionJob.status.in_([JobStatus.QUEUED, JobStatus.FAILED]),
            IngestionJob.run_after <= _now(),
        )
        .order_by(IngestionJob.run_after, IngestionJob.created_at)
        .limit(1)
        .with_for_update(skip_locked=True)
    ).first()
    if job is None:
        return None

    job.status = JobStatus.RUNNING
    job.attempts += 1
    job.locked_by = worker_id
    job.locked_at = _now()
    job.started_at = _now()
    job.error_message = None
    db.commit()
    db.refresh(job)
    return job


def succeed(db: Session, job: IngestionJob) -> None:
    job.status = JobStatus.SUCCEEDED
    job.finished_at = _now()
    job.locked_by = None
    if job.started_at:
        job.duration_seconds = (job.finished_at - job.started_at).total_seconds()
    db.commit()


def fail(db: Session, job: IngestionJob, error: str, *, retryable: bool = True) -> None:
    """Record a failure and schedule the retry, or bury the job."""
    job.finished_at = _now()
    job.locked_by = None
    job.error_message = error[:4000]
    if job.started_at:
        job.duration_seconds = (job.finished_at - job.started_at).total_seconds()

    if not retryable or job.attempts >= job.max_attempts:
        job.status = JobStatus.DEAD
        logger.error("job %s is dead after %s attempt(s): %s", job.id, job.attempts, error[:300])
    else:
        delay = backoff_seconds(
            job.attempts,
            base=settings.job_backoff_base_seconds,
            maximum=settings.job_backoff_max_seconds,
            jitter_key=str(job.id),
        )
        job.status = JobStatus.FAILED
        job.run_after = _now() + timedelta(seconds=delay)
        logger.warning(
            "job %s failed (attempt %s/%s), retrying in %.0fs: %s",
            job.id,
            job.attempts,
            job.max_attempts,
            delay,
            error[:300],
        )
    db.commit()


def reap_stale(db: Session) -> int:
    """Return jobs abandoned by a crashed worker to the queue."""
    cutoff = _now() - timedelta(seconds=settings.job_stale_seconds)
    result = db.execute(
        update(IngestionJob)
        .where(IngestionJob.status == JobStatus.RUNNING, IngestionJob.locked_at < cutoff)
        .values(
            status=JobStatus.FAILED,
            locked_by=None,
            error_message="worker went away; requeued",
            run_after=_now(),
        )
    )
    if result.rowcount:
        db.commit()
        logger.warning("requeued %s stale job(s)", result.rowcount)
    return result.rowcount or 0


def stats(db: Session) -> dict[str, int]:
    from sqlalchemy import func

    rows = db.execute(
        select(IngestionJob.status, func.count()).group_by(IngestionJob.status)
    ).all()
    return {status: count for status, count in rows}
