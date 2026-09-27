"""Durable ingestion queue on PostgreSQL.

Why a table instead of `BackgroundTasks`: the plan requires "background processing
with per-job status, retry with backoff, and a failed state". An in-process task list
loses every queued job when Render restarts the dyno, which makes per-job status a
fiction and retry impossible. A table costs one `SELECT ... FOR UPDATE SKIP LOCKED`
and buys durability, visibility, and safe concurrency.

Leases (audit finding 13): a claimed job's `locked_at` is its lease. The worker renews
it with `heartbeat()` while the job runs; `reap_stale()` only requeues jobs whose lease
has not been renewed for `JOB_STALE_SECONDS`. `succeed()`/`fail()` refuse to overwrite
a job that another worker has since reclaimed.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import and_, or_, select, update
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.logging import get_logger
from app.db.models import Document, IngestionJob, JobStatus
from app.security.labels import SourceType
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
    user_initiated: bool = True,
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
        payload={"user_initiated": True} if user_initiated else None,
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
    user_initiated: bool = True,
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
        payload={"vendor_source_id": str(vendor_source_id), "user_initiated": user_initiated},
    )
    db.add(job)
    db.commit()
    db.refresh(job)
    return job


def claim(db: Session, worker_id: str) -> IngestionJob | None:
    """Atomically claim the next runnable job. Safe to run from several workers."""
    reap_stale(db)
    stmt = select(IngestionJob).where(
        IngestionJob.status.in_([JobStatus.QUEUED, JobStatus.FAILED]),
        IngestionJob.run_after <= _now(),
    )
    if not settings.freshness_worker_enabled:
        # Legacy crawl and vendor-page ingestion jobs have no consent flag. Keep
        # them queued without letting them starve uploads or spend tokens after
        # scheduled crawling is switched off. Explicit checks can still run.
        requested = IngestionJob.payload["user_initiated"].as_boolean().is_(True)
        vendor_page = select(Document.id).where(
            Document.id == IngestionJob.document_id,
            Document.source_type == str(SourceType.VENDOR_PAGE),
        ).exists()
        stmt = stmt.where(or_(requested, and_(IngestionJob.kind != "freshness_crawl", ~vendor_page)))
    job = db.scalars(
        stmt.order_by(IngestionJob.run_after, IngestionJob.created_at)
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


def heartbeat(db: Session, job_id: uuid.UUID, worker_id: str) -> bool:
    """Renew the lease on a running job. False means another worker owns it now."""
    result = db.execute(
        update(IngestionJob)
        .where(
            IngestionJob.id == job_id,
            IngestionJob.status == JobStatus.RUNNING,
            IngestionJob.locked_by == worker_id,
        )
        .values(locked_at=_now())
        .execution_options(synchronize_session=False)
    )
    db.commit()
    return bool(result.rowcount)


def _taken_over(db: Session, job: IngestionJob) -> bool:
    """True when the DB shows this job RUNNING under a different worker."""
    mine = job.locked_by
    if not mine:
        return False
    row = db.execute(
        select(IngestionJob.status, IngestionJob.locked_by).where(IngestionJob.id == job.id)
    ).one_or_none()
    if row is None:
        return False
    status, owner = row
    return status == JobStatus.RUNNING and owner is not None and owner != mine


def succeed(db: Session, job: IngestionJob) -> None:
    if _taken_over(db, job):
        logger.warning("job %s finished after its lease was taken over; leaving the new owner's state", job.id)
        db.expire(job)
        return
    job.status = JobStatus.SUCCEEDED
    job.finished_at = _now()
    job.locked_by = None
    if job.started_at:
        job.duration_seconds = (job.finished_at - job.started_at).total_seconds()
    db.commit()


def fail(db: Session, job: IngestionJob, error: str, *, retryable: bool = True) -> None:
    """Record a failure and schedule the retry, or bury the job."""
    if _taken_over(db, job):
        logger.warning("job %s failed after its lease was taken over; leaving the new owner's state", job.id)
        db.expire(job)
        return
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
    """Return jobs whose lease expired (worker crashed or stopped renewing) to the queue."""
    cutoff = _now() - timedelta(seconds=settings.job_stale_seconds)
    result = db.execute(
        update(IngestionJob)
        .where(IngestionJob.status == JobStatus.RUNNING, IngestionJob.locked_at < cutoff)
        .values(
            status=JobStatus.FAILED,
            locked_by=None,
            error_message="lease expired (worker went away); requeued",
            run_after=_now(),
        )
        .execution_options(synchronize_session=False)
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
