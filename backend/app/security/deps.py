"""FastAPI dependencies for authentication, tenant resolution, and database scoping.

Phase 0 security baseline:
- Authenticates via cryptographic JWT (Authorization: Bearer <token>)
- Scopes sessions to the authenticated tenant for PostgreSQL Row-Level Security
- Provides owner_dev fallback for local development and testing
"""

from __future__ import annotations

import uuid
from collections.abc import Iterator

from fastapi import Depends, Header, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.models import AccessGrant, Organization
from app.db.session import get_db, get_tenant_db
from app.security.jwt import JWTError, decode_jwt
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
        return uuid.UUID(str(value))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=f"{field} is not a valid UUID") from exc


def resolve_principal(
    db: Session = Depends(get_db),
    authorization: str | None = Header(default=None),
) -> Principal:
    """Resolve the authenticated principal from a cryptographic Bearer token.

    Replaces developer header spoofing with signed JWT validation.
    When `settings.auth_mode == 'owner_dev'`, allows unauthenticated requests
    to resolve to the default organization owner for local development.
    """
    org = get_or_create_default_org(db)

    # 1. Bearer token verification
    if authorization and authorization.startswith("Bearer "):
        token = authorization[len("Bearer ") :].strip()
        try:
            payload = decode_jwt(token)
        except JWTError as exc:
            raise HTTPException(
                status_code=401,
                detail=f"invalid or expired token: {exc}",
                headers={"WWW-Authenticate": "Bearer"},
            ) from exc

        org_id = _parse_uuid(payload.get("org_id"), "org_id") or org.id
        user_id = _parse_uuid(payload.get("sub") or payload.get("user_id"), "user_id")
        raw_role = payload.get("role", Role.VIEWER)
        try:
            role = normalize(raw_role, Role, Role.VIEWER)
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

        max_sensitivity = payload.get("max_sensitivity", Sensitivity.INTERNAL.value)
        allow_vendor_restricted = bool(payload.get("allow_vendor_restricted", False))
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
            account_refs=frozenset(accounts) if accounts else frozenset(),
            include_unapproved=role != Role.VIEWER,
            label="jwt",
            grants=tuple(str(g.id) for g in grants),
        )

    # 2. Local dev bypass when explicitly enabled
    if settings.auth_mode == "owner_dev":
        return owner_principal(org.id)

    # 3. Unauthenticated request rejected
    raise HTTPException(
        status_code=401,
        detail="authentication required: provide Authorization: Bearer <token>",
        headers={"WWW-Authenticate": "Bearer"},
    )


def get_db_for_principal(
    principal: Principal = Depends(resolve_principal),
) -> Iterator[Session]:
    """Yield a database session with PostgreSQL Row-Level Security scoped to the principal's tenant."""
    yield from get_tenant_db(principal.org_id)
