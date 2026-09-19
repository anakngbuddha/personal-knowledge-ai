"""FastAPI dependency that turns a request into a `Principal`.

Isolated from `app.security.principal` so the principal model stays importable
without FastAPI or a database, which keeps the authorization unit tests fast.
"""

from __future__ import annotations

import uuid

from fastapi import Depends, Header, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.models import AccessGrant, Organization
from app.db.session import get_db
from app.security.labels import Role, Sensitivity, normalize
from app.security.principal import Principal, owner_principal


def get_or_create_default_org(db: Session) -> Organization:
    org = db.scalars(
        select(Organization).where(Organization.slug == settings.default_org_slug)
    ).first()
    if org is None:
        org = Organization(slug=settings.default_org_slug, name=settings.default_org_name)
        db.add(org)
        db.commit()
        db.refresh(org)
    return org


def _parse_uuid(value: str | None, field: str) -> uuid.UUID | None:
    if not value:
        return None
    try:
        return uuid.UUID(value)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=f"{field} is not a valid UUID") from exc


def resolve_principal(
    db: Session = Depends(get_db),
    x_org_id: str | None = Header(default=None),
    x_user_id: str | None = Header(default=None),
    x_user_role: str | None = Header(default=None),
) -> Principal:
    org = get_or_create_default_org(db)

    if settings.auth_mode == "owner_dev":
        return owner_principal(org.id)

    if settings.auth_mode != "dev_headers":
        raise HTTPException(
            status_code=503,
            detail="authentication is not configured (Phase 0 is not built)",
        )

    org_id = _parse_uuid(x_org_id, "X-Org-Id") or org.id
    user_id = _parse_uuid(x_user_id, "X-User-Id")
    try:
        role = normalize(x_user_role, Role, Role.VIEWER)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    if role in (Role.OWNER, Role.ADMIN):
        return owner_principal(org_id, user_id)

    grants = (
        list(
            db.scalars(
                select(AccessGrant).where(
                    AccessGrant.org_id == org_id, AccessGrant.user_id == user_id
                )
            )
        )
        if user_id
        else []
    )

    max_sensitivity = Sensitivity.INTERNAL.value
    allow_vendor_restricted = False
    accounts: set[str] = set()
    for grant in grants:
        if grant.account_ref:
            accounts.add(grant.account_ref)
        allow_vendor_restricted = allow_vendor_restricted or bool(grant.allow_vendor_restricted)
        if grant.max_sensitivity:
            from app.security.labels import sensitivity_rank

            if sensitivity_rank(grant.max_sensitivity) > sensitivity_rank(max_sensitivity):
                max_sensitivity = grant.max_sensitivity

    return Principal(
        org_id=org_id,
        user_id=user_id,
        role=role,
        max_sensitivity=max_sensitivity,
        allow_vendor_restricted=allow_vendor_restricted,
        account_refs=frozenset(accounts),
        include_unapproved=role != Role.VIEWER,
        label="dev_headers",
        grants=tuple(str(g.id) for g in grants),
    )
