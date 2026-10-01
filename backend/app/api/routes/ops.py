"""Phase 10 operations: restore drills and SSO status."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.errors import AppError
from app.db.models import RestoreDrill, SsoProtocol, SsoProvider
from app.db.session import get_db
from app.ops.restore import run_restore_drill
from app.security.audit import record_audit
from app.security.deps import resolve_principal
from app.security.principal import Principal
from app.sso import credentials
from app.sso.oidc import env_oidc_configured
from app.sso.service import load_provider

router = APIRouter(tags=["ops"])


class RestoreDrillOut(BaseModel):
    id: str
    status: str
    sla_seconds: float
    duration_seconds: float | None = None
    within_sla: bool | None = None
    row_counts_before: dict | None = None
    row_counts_after: dict | None = None
    error_message: str | None = None
    started_at: str | None = None
    finished_at: str | None = None


class RestoreDrillListOut(BaseModel):
    drills: list[RestoreDrillOut]
    total: int
    limit: int
    offset: int


class RestoreDrillIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    sla_seconds: float | None = Field(None, ge=0.05, le=3600)


class SsoStatusOut(BaseModel):
    sso_enabled: bool
    oidc_configured: bool
    saml_configured: bool
    oidc_issuer: str | None = None
    saml_issuer: str | None = None
    oidc_client_id: str | None = None


class SsoProviderIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    protocol: str = Field(..., pattern="^(oidc|saml)$")
    enabled: bool = False
    issuer: str = Field(..., min_length=3, max_length=512)
    client_id: str | None = Field(None, max_length=255)
    audience: str | None = Field(None, max_length=255)
    secret: str | None = Field(None, max_length=4096)


class SsoProviderOut(BaseModel):
    id: str
    protocol: str
    enabled: bool
    issuer: str
    client_id: str | None = None
    audience: str | None = None
    has_secret: bool = False


def _drill_out(row: RestoreDrill) -> RestoreDrillOut:
    return RestoreDrillOut(
        id=str(row.id),
        status=row.status,
        sla_seconds=row.sla_seconds,
        duration_seconds=row.duration_seconds,
        within_sla=row.within_sla,
        row_counts_before=row.row_counts_before,
        row_counts_after=row.row_counts_after,
        error_message="restore drill failed" if row.error_message else None,
        started_at=row.started_at.isoformat() if row.started_at else None,
        finished_at=row.finished_at.isoformat() if row.finished_at else None,
    )


@router.get("/ops/restore-drills", response_model=RestoreDrillListOut)
def list_drills(
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0, le=10000),
    db: Session = Depends(get_db),
    principal: Principal = Depends(resolve_principal),
) -> RestoreDrillListOut:
    if not principal.is_admin:
        raise HTTPException(status_code=403, detail="admin role required")
    filters = [RestoreDrill.org_id == principal.org_id]
    total = db.scalar(select(func.count()).select_from(RestoreDrill).where(*filters)) or 0
    rows = list(
        db.scalars(
            select(RestoreDrill)
            .where(*filters)
            .order_by(RestoreDrill.started_at.desc())
            .limit(limit)
            .offset(offset)
        )
    )
    return RestoreDrillListOut(
        drills=[_drill_out(row) for row in rows],
        total=int(total),
        limit=limit,
        offset=offset,
    )


@router.post("/ops/restore-drills", response_model=RestoreDrillOut, status_code=201)
def start_drill(
    payload: RestoreDrillIn | None = None,
    db: Session = Depends(get_db),
    principal: Principal = Depends(resolve_principal),
) -> RestoreDrillOut:
    if not principal.is_admin:
        raise HTTPException(status_code=403, detail="admin role required")
    sla = payload.sla_seconds if payload else None
    drill = run_restore_drill(
        db,
        org_id=principal.org_id,
        triggered_by=principal.user_id,
        sla_seconds=sla,
    )
    record_audit(
        db,
        principal,
        "restore_drill",
        "restore_drill",
        str(drill.id),
        {"status": drill.status, "within_sla": drill.within_sla},
    )
    return _drill_out(drill)


@router.get("/ops/sso", response_model=SsoStatusOut)
def sso_status(
    db: Session = Depends(get_db),
    principal: Principal = Depends(resolve_principal),
) -> SsoStatusOut:
    if not principal.is_admin:
        raise HTTPException(403, "admin access required")
    oidc_row = load_provider(db, principal.org_id, SsoProtocol.OIDC)
    saml_row = load_provider(db, principal.org_id, SsoProtocol.SAML)
    oidc_configured = bool((oidc_row and oidc_row.enabled) or env_oidc_configured())
    saml_configured = bool(
        (saml_row and saml_row.enabled) or (settings.sso_enabled and settings.saml_idp_issuer)
    )
    return SsoStatusOut(
        sso_enabled=settings.sso_enabled or oidc_configured or saml_configured,
        oidc_configured=oidc_configured,
        saml_configured=saml_configured,
        oidc_issuer=(oidc_row.issuer if oidc_row else settings.oidc_issuer) or None,
        saml_issuer=(saml_row.issuer if saml_row else settings.saml_idp_issuer) or None,
        oidc_client_id=(oidc_row.client_id if oidc_row else settings.oidc_client_id) or None,
    )


@router.put("/ops/sso/{protocol}", response_model=SsoProviderOut)
def upsert_sso(
    protocol: str,
    payload: SsoProviderIn,
    db: Session = Depends(get_db),
    principal: Principal = Depends(resolve_principal),
) -> SsoProviderOut:
    if not principal.is_admin:
        raise HTTPException(status_code=403, detail="admin role required")
    if protocol != payload.protocol:
        raise HTTPException(status_code=400, detail="protocol path does not match body")
    row = load_provider(db, principal.org_id, protocol)
    if row is None:
        row = SsoProvider(
            org_id=principal.org_id,
            protocol=protocol,
            issuer=payload.issuer,
            enabled=payload.enabled,
            client_id=payload.client_id,
            audience=payload.audience,
        )
        db.add(row)
    else:
        row.issuer = payload.issuer
        row.enabled = payload.enabled
        row.client_id = payload.client_id
        row.audience = payload.audience
    if payload.secret:
        try:
            row.secret_ciphertext = credentials.encrypt_secret(payload.secret)
        except AppError as exc:
            raise HTTPException(status_code=exc.status_code, detail=exc.message) from exc
    db.commit()
    db.refresh(row)
    record_audit(db, principal, "upsert", "sso_provider", str(row.id), {"protocol": protocol})
    return SsoProviderOut(
        id=str(row.id),
        protocol=row.protocol,
        enabled=row.enabled,
        issuer=row.issuer,
        client_id=row.client_id,
        audience=row.audience,
        has_secret=bool(row.secret_ciphertext),
    )
