import uuid

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import IngestionJob
from app.db.session import get_db
from app.jobs import queue
from app.security.deps import resolve_principal
from app.security.principal import Principal

router = APIRouter(prefix="/jobs", tags=["ingestion jobs"])


class JobOut(BaseModel):
    id: uuid.UUID
    document_id: uuid.UUID
    kind: str
    status: str
    attempts: int
    max_attempts: int
    run_after: str | None = None
    duration_seconds: float | None = None
    error_message: str | None = None


class QueueStatsOut(BaseModel):
    counts: dict[str, int]
    requeued_stale: int


@router.get("", response_model=list[JobOut])
def list_jobs(
    status_filter: str | None = None,
    limit: int = 50,
    db: Session = Depends(get_db),
    principal: Principal = Depends(resolve_principal),
) -> list[JobOut]:
    """Per-job status. Every failure is individually explainable and retryable, which
    is the Phase 1 exit criterion."""
    statement = select(IngestionJob).where(IngestionJob.org_id == principal.org_id)
    if status_filter:
        statement = statement.where(IngestionJob.status == status_filter)
    rows = db.scalars(
        statement.order_by(IngestionJob.created_at.desc()).limit(min(max(limit, 1), 200))
    )
    return [
        JobOut(
            id=row.id,
            document_id=row.document_id,
            kind=row.kind,
            status=row.status,
            attempts=row.attempts,
            max_attempts=row.max_attempts,
            run_after=row.run_after.isoformat() if row.run_after else None,
            duration_seconds=row.duration_seconds,
            error_message=row.error_message,
        )
        for row in rows
    ]


@router.get("/stats", response_model=QueueStatsOut)
def job_stats(
    db: Session = Depends(get_db),
    principal: Principal = Depends(resolve_principal),
) -> QueueStatsOut:
    requeued = queue.reap_stale(db)
    return QueueStatsOut(counts=queue.stats(db), requeued_stale=requeued)
