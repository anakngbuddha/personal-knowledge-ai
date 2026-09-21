"""Tenant-scoped MCP integration rows."""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.models import McpIntegration
from app.mcp.servers import BRAVE, MS365, PLAYWRIGHT, SERVER_SLUGS


def get_integration(db: Session, org_id: uuid.UUID, slug: str) -> McpIntegration | None:
    return db.scalars(
        select(McpIntegration).where(
            McpIntegration.org_id == org_id,
            McpIntegration.server_slug == slug,
        )
    ).first()


def get_integration_by_id(
    db: Session, org_id: uuid.UUID, integration_id: uuid.UUID
) -> McpIntegration | None:
    return db.scalars(
        select(McpIntegration).where(
            McpIntegration.id == integration_id,
            McpIntegration.org_id == org_id,
        )
    ).first()


def list_integrations(db: Session, org_id: uuid.UUID) -> list[McpIntegration]:
    return list(
        db.scalars(select(McpIntegration).where(McpIntegration.org_id == org_id)).all()
    )


def upsert_integration(
    db: Session,
    *,
    org_id: uuid.UUID,
    slug: str,
    enabled: bool,
    config: dict[str, Any] | None,
    secret_ciphertext: bytes | None,
    status: str,
    last_error: str | None = None,
) -> McpIntegration:
    row = get_integration(db, org_id, slug)
    if row is None:
        row = McpIntegration(
            org_id=org_id,
            server_slug=slug,
            enabled=enabled,
            config=config or {},
            secret_ciphertext=secret_ciphertext,
            status=status,
            last_error=last_error,
        )
        db.add(row)
    else:
        row.enabled = enabled
        if config is not None:
            row.config = config
        if secret_ciphertext is not None:
            row.secret_ciphertext = secret_ciphertext
        row.status = status
        row.last_error = last_error
    db.commit()
    db.refresh(row)
    return row


def process_fallback_enabled(slug: str) -> bool:
    """Env-level enablement when the org has no row yet."""
    if not settings.mcp_enabled:
        return False
    if slug == BRAVE:
        return bool(settings.brave_api_key)
    if slug == PLAYWRIGHT:
        return bool(settings.mcp_playwright_enabled)
    if slug == MS365:
        return bool(settings.mcp_ms365_enabled)
    return False


def known_slug(slug: str) -> bool:
    return slug in SERVER_SLUGS
