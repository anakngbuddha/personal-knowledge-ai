"""Request authentication: bearer token -> Principal, with membership re-checked.

`principal_from_claims` is the single place a signed token becomes a Principal. Both
the web API (`resolve_principal`) and the MCP transport use it, so a revoked or
downgraded member loses access on the next request instead of at token expiry, and
no transport trusts a role claim over the membership table.

Token audiences are kept apart: MCP tokens (`typ: mcp`) are for the MCP transport
only and are refused by the web API, so a token pasted into a desktop client config
cannot drive the full REST surface.
"""

from __future__ import annotations

import dataclasses
import uuid
from collections.abc import Iterator
from typing import Any

from fastapi import Depends, Header, HTTPException
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.models import AccessGrant, Organization
from app.db.session import get_db, get_tenant_db, scope_session_to_org
from app.security.accounts import OrganizationMembership, UserAccount
from app.security.jwt import JWTError, decode_jwt
from app.security.labels import Role, Sensitivity, normalize
from app.security.principal import Principal, owner_principal

# Token types reserved for other transports and refused by the web API.
_NON_WEB_TOKEN_TYPES = frozenset({"mcp"})


def get_or_create_default_org(db: Session) -> Organization:
    org = db.scalars(select(Organization).where(Organization.slug == settings.default_org_slug)).first()
    if org is None:
        org = Organization(slug=settings.default_org_slug, name=settings.default_org_name)
        db.add(org)
        db.commit()
        db.refresh(org)
    return org


def is_production() -> bool:
    return settings.environment.lower() == "production"


def dev_fallback_allowed() -> bool:
    """Unauthenticated owner access exists only for local owner_dev work."""
    return settings.auth_mode == "owner_dev" and not is_production()


def _scopes_from(payload: dict[str, Any]) -> frozenset[str] | None:
    raw = payload.get("scope")
    if raw is None:
        return None
    if isinstance(raw, str):
        items = raw.split()
    elif isinstance(raw, (list, tuple)):
        items = [str(item) for item in raw]
    else:
        return frozenset()
    return frozenset(item.strip() for item in items if item and item.strip())


def _safe_normalize(value: Any, enum, default):
    try:
        return normalize(value if isinstance(value, str) else None, enum, default)
    except ValueError:
        return str(default)


def principal_from_claims(
    db: Session,
    payload: dict[str, Any],
    *,
    label: str = "jwt",
    default_org: Organization | None = None,
) -> Principal:
    """Build a Principal from verified token claims, re-checking membership and grants."""
    org = default_org or get_or_create_default_org(db)
    org_id = _uuid(payload.get("org_id")) or org.id
    user_id = _uuid(payload.get("sub") or payload.get("user_id"))
    # The bearer signature was verified before this function is called.
    scope_session_to_org(db, org_id)

    membership = None
    if user_id:
        try:
            membership = db.scalar(
                select(OrganizationMembership).join(UserAccount, UserAccount.id == OrganizationMembership.user_id).where(
                    OrganizationMembership.org_id == org_id,
                    OrganizationMembership.user_id == user_id,
                    UserAccount.is_active.is_(True),
                )
            )
        except SQLAlchemyError:
            db.rollback()  # legacy unit fixtures do not create account tables

    if membership is not None and not membership.is_active:
        raise HTTPException(403, "your access to this organization has been revoked")
    if is_production() and membership is None:
        raise HTTPException(403, "your account is not a member of this organization")

    # Membership and grant queries use the verified token's tenant scope.
    scope_session_to_org(db, org_id)

    # Membership is the source of truth. The role claim is only a dev-mode fallback
    # for tokens minted without an account.
    role = membership.role if membership else _safe_normalize(payload.get("role"), Role, Role.VIEWER)

    grants: list[AccessGrant] = []
    if user_id:
        try:
            grants = list(
                db.scalars(
                    select(AccessGrant).where(AccessGrant.org_id == org_id, AccessGrant.user_id == user_id)
                )
            )
        except SQLAlchemyError:
            db.rollback()
            grants = []
    grant_ids = tuple(str(g.id) for g in grants)
    scopes = _scopes_from(payload)

    if role == Role.OWNER:
        base = owner_principal(org_id, user_id)
        return dataclasses.replace(base, scopes=scopes, label="mcp" if label == "mcp" else base.label)
    if role == Role.ADMIN:
        return Principal(
            org_id=org_id,
            user_id=user_id,
            role=role,
            max_sensitivity=Sensitivity.CUSTOMER_DATA,
            allow_vendor_restricted=True,
            account_refs=None,
            include_unapproved=True,
            label=label,
            grants=grant_ids,
            scopes=scopes,
        )

    # Sensitivity claims are honored only on first-party session tokens. MCP tokens
    # get the role default plus explicit grants, nothing the token itself asserts.
    if label == "mcp":
        max_sensitivity = Sensitivity.INTERNAL.value
        allow_vendor = False
    else:
        max_sensitivity = _safe_normalize(payload.get("max_sensitivity"), Sensitivity, Sensitivity.INTERNAL)
        if max_sensitivity == Sensitivity.VENDOR_RESTRICTED:
            max_sensitivity = Sensitivity.INTERNAL.value
        allow_vendor = bool(payload.get("allow_vendor_restricted", False))
    accounts: set[str] = set()
    for grant in grants:
        if grant.account_ref:
            accounts.add(grant.account_ref)
        allow_vendor = allow_vendor or bool(grant.allow_vendor_restricted)
    return Principal(
        org_id=org_id,
        user_id=user_id,
        role=role,
        max_sensitivity=max_sensitivity,
        allow_vendor_restricted=allow_vendor,
        account_refs=frozenset(accounts),
        include_unapproved=False,
        label=label,
        grants=grant_ids,
        scopes=scopes,
    )


def resolve_principal(db: Session = Depends(get_db), authorization: str | None = Header(default=None)) -> Principal:
    org = get_or_create_default_org(db)
    if not authorization or not authorization.startswith("Bearer "):
        if dev_fallback_allowed():
            principal = owner_principal(org.id)
            scope_session_to_org(db, principal.org_id)
            return principal
        raise HTTPException(401, "authentication required: sign in first", headers={"WWW-Authenticate": "Bearer"})
    try:
        payload = decode_jwt(authorization[7:].strip())
    except JWTError as exc:
        raise HTTPException(401, "invalid or expired session", headers={"WWW-Authenticate": "Bearer"}) from exc
    if payload.get("typ") in _NON_WEB_TOKEN_TYPES:
        raise HTTPException(401, "this token is for MCP clients only; sign in to use the web API", headers={"WWW-Authenticate": "Bearer"})
    principal = principal_from_claims(db, payload, label="jwt", default_org=org)
    # The route's Depends(get_db) is this same session, so everything the route does
    # from here on runs under the tenant's RLS scope.
    scope_session_to_org(db, principal.org_id)
    return principal


def _uuid(value: object) -> uuid.UUID | None:
    try:
        return uuid.UUID(str(value)) if value else None
    except (ValueError, AttributeError, TypeError):
        return None


def get_db_for_principal(principal: Principal = Depends(resolve_principal)) -> Iterator[Session]:
    yield from get_tenant_db(principal.org_id)


def require_document_write(principal: Principal = Depends(resolve_principal)) -> Principal:
    if not principal.can_write_catalog:
        raise HTTPException(403, "solutions engineer role required")
    return principal


def require_document_approval(principal: Principal = Depends(resolve_principal)) -> Principal:
    if not principal.is_admin:
        raise HTTPException(403, "admin access required")
    return principal


def require_admin(principal: Principal = Depends(resolve_principal)) -> Principal:
    if not principal.is_admin:
        raise HTTPException(403, "admin access required")
    return principal
