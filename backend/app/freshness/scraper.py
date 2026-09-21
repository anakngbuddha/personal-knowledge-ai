"""SSRF-gated vendor URL checks. Hash changes raise staleness alerts."""

from __future__ import annotations

import hashlib
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.errors import AppError, SsrfBlocked
from app.db.models import FreshnessAlert, FreshnessStatus, VendorSource
from app.net.ssrf import validate_url


@dataclass(frozen=True)
class FetchSnapshot:
    data: bytes
    etag: str | None = None
    last_modified: str | None = None
    final_url: str | None = None


Fetcher = Callable[[str], FetchSnapshot]


@dataclass(frozen=True)
class CheckResult:
    source_id: uuid.UUID
    status: str
    hash: str | None
    changed: bool
    alert_id: uuid.UUID | None
    error: str | None = None


def _now() -> datetime:
    return datetime.now(timezone.utc)


def content_digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def default_fetcher(url: str) -> FetchSnapshot:
    from app.net.ssrf import fetch

    resource = fetch(url, max_bytes=settings.freshness_max_bytes)
    return FetchSnapshot(data=resource.data, final_url=resource.final_url)


def create_source(
    db: Session,
    *,
    org_id: uuid.UUID,
    workspace_id: uuid.UUID,
    label: str,
    url: str,
    product_id: uuid.UUID | None = None,
    check_interval_seconds: int | None = None,
) -> VendorSource:
    label = label.strip()
    if not label:
        raise AppError(status_code=400, code="source_label_required", message="label is required")
    # Syntax-only here; the fetch path still runs the full SSRF resolver.
    normalized, _ = validate_url(url, allow_private=True)
    existing = db.scalar(
        select(VendorSource).where(
            VendorSource.workspace_id == workspace_id, VendorSource.url == normalized
        )
    )
    if existing:
        raise AppError(status_code=409, code="source_exists", message="URL is already monitored")
    interval = check_interval_seconds or settings.freshness_default_interval_seconds
    source = VendorSource(
        org_id=org_id,
        workspace_id=workspace_id,
        product_id=product_id,
        label=label,
        url=normalized,
        check_interval_seconds=max(60, interval),
        status=FreshnessStatus.PENDING,
        next_check_at=_now(),
    )
    db.add(source)
    db.commit()
    db.refresh(source)
    return source


def check_source(
    db: Session,
    source: VendorSource,
    *,
    fetcher: Fetcher | None = None,
) -> CheckResult:
    """Fetch one vendor URL and raise a staleness alert when the digest changes."""
    fetch_fn = fetcher or default_fetcher
    previous = source.last_hash
    try:
        snapshot = fetch_fn(source.url)
    except SsrfBlocked as exc:
        source.status = FreshnessStatus.ERROR
        source.last_error = str(exc.message or exc)[:2000]
        source.last_checked_at = _now()
        source.next_check_at = _now() + timedelta(seconds=source.check_interval_seconds)
        source.locked_by = None
        source.locked_at = None
        db.commit()
        return CheckResult(
            source_id=source.id,
            status=source.status,
            hash=source.last_hash,
            changed=False,
            alert_id=None,
            error=source.last_error,
        )

    digest = content_digest(snapshot.data)
    changed = previous is not None and previous != digest
    alert_id: uuid.UUID | None = None
    source.last_hash = digest
    source.last_etag = snapshot.etag
    source.last_modified_header = snapshot.last_modified
    source.last_checked_at = _now()
    source.last_error = None
    source.next_check_at = _now() + timedelta(seconds=source.check_interval_seconds)
    source.locked_by = None
    source.locked_at = None
    if changed:
        source.status = FreshnessStatus.STALE
        alert = FreshnessAlert(
            org_id=source.org_id,
            vendor_source_id=source.id,
            kind="content_changed",
            previous_hash=previous,
            new_hash=digest,
            details={"url": source.url, "bytes": len(snapshot.data)},
        )
        db.add(alert)
        db.flush()
        alert_id = alert.id
    else:
        source.status = FreshnessStatus.FRESH
    db.commit()
    return CheckResult(
        source_id=source.id,
        status=source.status,
        hash=digest,
        changed=changed,
        alert_id=alert_id,
    )


def claim_due_source(db: Session, worker_id: str) -> VendorSource | None:
    now = _now()
    stmt = (
        select(VendorSource)
        .where(
            VendorSource.enabled.is_(True),
            VendorSource.next_check_at <= now,
        )
        .order_by(VendorSource.next_check_at)
        .limit(1)
    )
    bind = db.get_bind()
    if bind is not None and bind.dialect.name == "postgresql":
        stmt = stmt.with_for_update(skip_locked=True)
    source = db.scalars(stmt).first()
    if source is None:
        return None
    source.locked_by = worker_id
    source.locked_at = now
    db.commit()
    db.refresh(source)
    return source


def acknowledge_alert(
    db: Session,
    *,
    org_id: uuid.UUID,
    alert_id: uuid.UUID,
    user_id: uuid.UUID | None,
) -> FreshnessAlert:
    alert = db.scalar(
        select(FreshnessAlert).where(FreshnessAlert.id == alert_id, FreshnessAlert.org_id == org_id)
    )
    if alert is None:
        raise AppError(status_code=404, code="alert_not_found", message="alert not found")
    alert.acknowledged_at = _now()
    alert.acknowledged_by = user_id
    source = db.get(VendorSource, alert.vendor_source_id)
    if source is not None and source.status == FreshnessStatus.STALE:
        source.status = FreshnessStatus.FRESH
    db.commit()
    db.refresh(alert)
    return alert


def list_open_alerts(db: Session, *, org_id: uuid.UUID, limit: int = 50, offset: int = 0):
    from sqlalchemy import func

    filters = [FreshnessAlert.org_id == org_id, FreshnessAlert.acknowledged_at.is_(None)]
    total = db.scalar(select(func.count()).select_from(FreshnessAlert).where(*filters)) or 0
    rows = list(
        db.scalars(
            select(FreshnessAlert)
            .where(*filters)
            .order_by(FreshnessAlert.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
    )
    return rows, int(total)
