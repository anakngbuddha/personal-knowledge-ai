"""Phase 9 MCP integration admin API."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from app.core.errors import AppError
from app.db.session import get_db
from app.mcp.credentials import decrypt_secret, encrypt_secret, secret_configured
from app.mcp.sheets_tools import SheetTarget
from app.mcp.registry_bridge import ping_server
from app.mcp.sandbox import ALLOWED_BY_SLUG
from app.mcp.servers import (
    EXA,
    FIRECRAWL,
    GOOGLE_SHEETS,
    SERVER_SLUGS,
    STATUS_CONNECTED,
    STATUS_DISABLED,
    STATUS_DISCONNECTED,
    STATUS_ERROR,
)
from app.mcp.store import (
    get_integration,
    get_integration_by_id,
    known_slug,
    list_integrations,
    process_fallback_enabled,
    upsert_integration,
)
from app.security.audit import record_audit
from app.security.deps import resolve_principal
from app.security.principal import Principal
from app.tools.registry import ToolContext

router = APIRouter(tags=["integrations"])


class McpIntegrationOut(BaseModel):
    id: str | None = None
    server_slug: str
    enabled: bool
    status: str
    last_error: str | None = None
    has_secret: bool = False
    allowed_hosts: list[str] = Field(default_factory=list)
    http_url: str | None = None
    allowed_tools: list[str] = Field(default_factory=list)
    sheet_targets: list[SheetTarget] = Field(default_factory=list)


class McpIntegrationListOut(BaseModel):
    mcp_enabled: bool
    integrations: list[McpIntegrationOut]


class McpIntegrationUpsertIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    enabled: bool = False
    secret: str | None = Field(default=None, max_length=8192)
    allowed_hosts: list[str] = Field(default_factory=list, max_length=50)
    http_url: str | None = Field(default=None, max_length=2048)
    sheet_targets: list[SheetTarget] | None = Field(default=None, max_length=50)


class McpPingOut(BaseModel):
    server: str
    status: str
    tools: list[str] = Field(default_factory=list)


def _require_reader(principal: Principal) -> None:
    if not principal.can_write_catalog:
        raise HTTPException(status_code=403, detail="solutions engineer role required")


def _require_admin(principal: Principal) -> None:
    if not principal.is_admin:
        raise HTTPException(status_code=403, detail="admin role required")


def _serialize(slug: str, row) -> McpIntegrationOut:
    config = (row.config if row is not None else None) or {}
    enabled = bool(row.enabled) if row is not None else process_fallback_enabled(slug)
    status = row.status if row is not None else (
        STATUS_DISCONNECTED if enabled else STATUS_DISABLED
    )
    return McpIntegrationOut(
        id=str(row.id) if row is not None else None,
        server_slug=slug,
        enabled=enabled,
        status=status,
        last_error=row.last_error if row is not None else None,
        has_secret=bool(row.secret_ciphertext) if row is not None else False,
        allowed_hosts=list(config.get("allowed_hosts") or []),
        http_url=config.get("http_url"),
        allowed_tools=sorted(ALLOWED_BY_SLUG.get(slug, ())),
        sheet_targets=config.get("sheet_targets", []) if slug == GOOGLE_SHEETS else [],
    )


@router.get("/integrations/mcp", response_model=McpIntegrationListOut)
def list_mcp_integrations(
    db: Session = Depends(get_db),
    principal: Principal = Depends(resolve_principal),
) -> McpIntegrationListOut:
    _require_reader(principal)
    from app.core.config import settings

    rows = {row.server_slug: row for row in list_integrations(db, principal.org_id)}
    return McpIntegrationListOut(
        mcp_enabled=settings.mcp_enabled,
        integrations=[_serialize(slug, rows.get(slug)) for slug in SERVER_SLUGS],
    )


@router.get("/integrations/mcp/{integration_id}", response_model=McpIntegrationOut)
def get_mcp_integration(
    integration_id: uuid.UUID,
    db: Session = Depends(get_db),
    principal: Principal = Depends(resolve_principal),
) -> McpIntegrationOut:
    _require_reader(principal)
    row = get_integration_by_id(db, principal.org_id, integration_id)
    if row is None:
        raise HTTPException(status_code=404, detail="not found")
    return _serialize(row.server_slug, row)


@router.put("/integrations/mcp/{server_slug}", response_model=McpIntegrationOut)
def upsert_mcp_integration(
    server_slug: str,
    payload: McpIntegrationUpsertIn,
    db: Session = Depends(get_db),
    principal: Principal = Depends(resolve_principal),
) -> McpIntegrationOut:
    _require_admin(principal)
    if not known_slug(server_slug):
        raise HTTPException(status_code=404, detail="not found")
    if server_slug in (EXA, FIRECRAWL, GOOGLE_SHEETS) and payload.http_url:
        raise HTTPException(status_code=422, detail="integration endpoints are fixed by the platform")
    existing = get_integration(db, principal.org_id, server_slug)
    config = dict(existing.config or {}) if existing is not None else {}
    if payload.sheet_targets is not None:
        if server_slug != GOOGLE_SHEETS:
            raise HTTPException(422, "sheet targets apply only to Google Sheets")
        aliases = [target.alias for target in payload.sheet_targets]
        if len(set(aliases)) != len(aliases):
            raise HTTPException(422, "sheet aliases must be unique")
        from sqlalchemy import select
        from app.db.models import Workspace
        for target in payload.sheet_targets:
            workspace = db.scalars(select(Workspace).where(
                Workspace.id == target.workspace_id, Workspace.org_id == principal.org_id,
            )).first()
            if workspace is None:
                raise HTTPException(422, "sheet target workspace is outside the tenant")
        config["sheet_targets"] = [target.model_dump(mode="json") for target in payload.sheet_targets]
    hosts = [h.strip() for h in payload.allowed_hosts if h and h.strip()]
    for host in hosts:
        if len(host) > 253:
            raise HTTPException(status_code=400, detail="allowed host is too long")
    config["allowed_hosts"] = hosts
    if payload.http_url:
        config["http_url"] = payload.http_url
    elif "http_url" in config and payload.http_url is None:
        # omit means leave unchanged unless explicitly empty string — extra=forbid
        # uses None as "unchanged" for http_url when not rotating.
        pass
    ciphertext = existing.secret_ciphertext if existing is not None else None
    if payload.secret:
        if not secret_configured():
            raise HTTPException(status_code=500, detail="MCP_CREDENTIALS_KEY is not configured")
        if server_slug == GOOGLE_SHEETS:
            from app.sales.sheets import validate_service_account_config
            try:
                validate_service_account_config(payload.secret)
            except ValueError as exc:
                raise HTTPException(status_code=422, detail=str(exc)) from exc
        ciphertext = encrypt_secret(payload.secret)
    if server_slug in (EXA, FIRECRAWL, GOOGLE_SHEETS) and payload.enabled and not ciphertext:
        raise HTTPException(status_code=422, detail="integration requires tenant credentials")
    status = STATUS_DISCONNECTED if payload.enabled else STATUS_DISABLED
    row = upsert_integration(
        db,
        org_id=principal.org_id,
        slug=server_slug,
        enabled=payload.enabled,
        config=config,
        secret_ciphertext=ciphertext,
        status=status,
        last_error=None,
    )
    record_audit(
        db,
        principal,
        action="mcp_upsert",
        resource_type="mcp_integration",
        resource_id=server_slug,
        details={"enabled": payload.enabled, "has_secret": bool(payload.secret)},
    )
    return _serialize(server_slug, row)


@router.post("/integrations/mcp/{server_slug}/test", response_model=McpPingOut)
def test_mcp_integration(
    server_slug: str,
    db: Session = Depends(get_db),
    principal: Principal = Depends(resolve_principal),
) -> McpPingOut:
    _require_admin(principal)
    if not known_slug(server_slug):
        raise HTTPException(status_code=404, detail="not found")
    if server_slug == GOOGLE_SHEETS:
        row = get_integration(db, principal.org_id, server_slug)
        if row is None or not row.enabled or not row.secret_ciphertext:
            raise HTTPException(status_code=409, detail="tenant Google Sheets integration is not configured")
        from app.sales.sheets import SheetExportError, service_account_access_token
        try:
            service_account_access_token(decrypt_secret(row.secret_ciphertext))
        except (AppError, SheetExportError) as exc:
            row.status = STATUS_ERROR
            row.last_error = "Google Sheets authorization failed"
            db.commit()
            raise HTTPException(status_code=502, detail="Google Sheets authorization failed") from exc
        row.status = STATUS_CONNECTED
        row.last_error = None
        db.commit()
        record_audit(db, principal, "mcp_test", "mcp_integration", server_slug,
                     {"server": server_slug, "tool_count": 3})
        return McpPingOut(server=server_slug, status=STATUS_CONNECTED,
                          tools=["export_issued_quote", "read_sheet", "write_draft"])
    workspace_id = uuid.uuid4()
    ctx = ToolContext(db=db, principal=principal, workspace_id=workspace_id)
    try:
        result = ping_server(ctx, server_slug)
    except AppError as exc:
        row = get_integration(db, principal.org_id, server_slug)
        if row is not None:
            row.status = STATUS_ERROR
            row.last_error = exc.message
            db.commit()
        raise HTTPException(status_code=exc.status_code, detail=exc.message) from exc
    row = get_integration(db, principal.org_id, server_slug)
    if row is not None:
        row.status = STATUS_CONNECTED
        row.last_error = None
        db.commit()
    record_audit(
        db,
        principal,
        action="mcp_test",
        resource_type="mcp_integration",
        resource_id=server_slug,
        details={"server": server_slug, "tool_count": len(result.get("tools") or [])},
    )
    return McpPingOut(
        server=result["server"],
        status=result["status"],
        tools=list(result.get("tools") or []),
    )
