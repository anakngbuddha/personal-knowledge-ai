"""Audit logging utilities for Phase 0 security baseline.

Records append-only security and operational events to the audit_logs table.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from app.db.models import AuditLog
from app.security.principal import Principal


def record_audit(
    db: Session,
    principal: Principal,
    action: str,
    resource_type: str,
    resource_id: str | None = None,
    details: dict[str, Any] | None = None,
) -> AuditLog:
    """Record an append-only audit log entry."""
    entry = AuditLog(
        org_id=principal.org_id,
        user_id=principal.user_id,
        action=action,
        resource_type=resource_type,
        resource_id=resource_id,
        details=details,
    )
    db.add(entry)
    db.commit()
    db.refresh(entry)
    return entry
