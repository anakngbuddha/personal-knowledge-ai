"""Phase 10 vendor freshness monitoring API."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.errors import AppError
from app.db.models import FreshnessAlert, VendorSource
from app.db.session import get_db
from app.documents.service import get_or_create_default_workspace
from app.freshness.scraper import acknowledge_alert, check_source, create_source
from app.security.audit import record_audit
from app.security.deps import resolve_principal
from app.security.principal import Principal

router = APIRouter(prefix="/freshness", tags=["freshness"])


class VendorSourceIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    label: str = Field(..., min_length=1, max_length=255)
    url: str = Field(..., min_length=8, max_length=2048)
    product_id: uuid.UUID | None = None
    check_interval_seconds: int | None = Field(None, ge=60, le=2_592_000)


class VendorSourceOut(BaseModel):
    id: str
    label: str
    url: str
    status: str
    enabled: bool
    last_hash: str | None = None
    last_checked_at: str | None = None
    next_check_at: str | None = None
    last_error: str | None = None
    product_id: str | None = None


class VendorSourceListOut(BaseModel):
    sources: list[VendorSourceOut]
    total: int
    limit: int
    offset: int


class FreshnessAlertOut(BaseModel):
    id: str
    vendor_source_id: str
    kind: str
    previous_hash: str | None = None
    new_hash: str | None = None
    created_at: str | None = None
    acknowledged_at: str | None = None


class FreshnessAlertListOut(BaseModel):
    alerts: list[FreshnessAlertOut]
    total: int
    limit: int
    offset: int


class CheckOut(BaseModel):
    source_id: str
    status: str
    hash: str | None = None
    changed: bool
    alert_id: str | None = None
    error: str | None = None


def _http(exc: AppError) -> HTTPException:
    return HTTPException(status_code=exc.status_code, detail=exc.message)


def _source_out(row: VendorSource) -> VendorSourceOut:
    return VendorSourceOut(
        id=str(row.id),
        label=row.label,
        url=row.url,
        status=row.status,
        enabled=row.enabled,
        last_hash=row.last_hash,
        last_checked_at=row.last_checked_at.isoformat() if row.last_checked_at else None,
        next_check_at=row.next_check_at.isoformat() if row.next_check_at else None,
        last_error=row.last_error,
        product_id=str(row.product_id) if row.product_id else None,
    )


def _alert_out(row: FreshnessAlert) -> FreshnessAlertOut:
    return FreshnessAlertOut(
        id=str(row.id),
        vendor_source_id=str(row.vendor_source_id),
        kind=row.kind,
        previous_hash=row.previous_hash,
        new_hash=row.new_hash,
        created_at=row.created_at.isoformat() if row.created_at else None,
        acknowledged_at=row.acknowledged_at.isoformat() if row.acknowledged_at else None,
    )


@router.get("/sources", response_model=VendorSourceListOut)
def list_sources(
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
    principal: Principal = Depends(resolve_principal),
) -> VendorSourceListOut:
    filters = [VendorSource.org_id == principal.org_id]
    total = db.scalar(select(func.count()).select_from(VendorSource).where(*filters)) or 0
    rows = list(
        db.scalars(
            select(VendorSource)
            .where(*filters)
            .order_by(VendorSource.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
    )
    return VendorSourceListOut(
        sources=[_source_out(row) for row in rows],
        total=int(total),
        limit=limit,
        offset=offset,
    )


@router.post("/sources", response_model=VendorSourceOut, status_code=201)
def add_source(
    payload: VendorSourceIn,
    db: Session = Depends(get_db),
    principal: Principal = Depends(resolve_principal),
) -> VendorSourceOut:
    if not principal.can_write_catalog:
        raise HTTPException(status_code=403, detail="solutions engineer role required")
    workspace = get_or_create_default_workspace(db, principal.org_id)
    try:
        source = create_source(
            db,
            org_id=principal.org_id,
            workspace_id=workspace.id,
            label=payload.label,
            url=str(payload.url),
            product_id=payload.product_id,
            check_interval_seconds=payload.check_interval_seconds,
        )
    except AppError as exc:
        raise _http(exc) from exc
    record_audit(db, principal, "create", "vendor_source", str(source.id), {"url": source.url})
    return _source_out(source)


@router.post("/sources/{source_id}/check", response_model=CheckOut)
def run_check(
    source_id: uuid.UUID,
    db: Session = Depends(get_db),
    principal: Principal = Depends(resolve_principal),
) -> CheckOut:
    if not principal.can_write_catalog:
        raise HTTPException(status_code=403, detail="solutions engineer role required")
    source = db.scalar(
        select(VendorSource).where(VendorSource.id == source_id, VendorSource.org_id == principal.org_id)
    )
    if source is None:
        raise HTTPException(status_code=404, detail="not found")
    result = check_source(db, source)
    record_audit(
        db,
        principal,
        "check",
        "vendor_source",
        str(source.id),
        {"status": result.status, "changed": result.changed},
    )
    return CheckOut(
        source_id=str(result.source_id),
        status=result.status,
        hash=result.hash,
        changed=result.changed,
        alert_id=str(result.alert_id) if result.alert_id else None,
        error=result.error,
    )


@router.get("/alerts", response_model=FreshnessAlertListOut)
def list_alerts(
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
    principal: Principal = Depends(resolve_principal),
) -> FreshnessAlertListOut:
    from app.freshness.scraper import list_open_alerts

    rows, total = list_open_alerts(db, org_id=principal.org_id, limit=limit, offset=offset)
    return FreshnessAlertListOut(
        alerts=[_alert_out(row) for row in rows],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.post("/alerts/{alert_id}/ack", response_model=FreshnessAlertOut)
def ack_alert(
    alert_id: uuid.UUID,
    db: Session = Depends(get_db),
    principal: Principal = Depends(resolve_principal),
) -> FreshnessAlertOut:
    if not principal.can_write_catalog:
        raise HTTPException(status_code=403, detail="solutions engineer role required")
    try:
        alert = acknowledge_alert(db, org_id=principal.org_id, alert_id=alert_id, user_id=principal.user_id)
    except AppError as exc:
        raise _http(exc) from exc
    record_audit(db, principal, "acknowledge", "freshness_alert", str(alert.id))
    return _alert_out(alert)
