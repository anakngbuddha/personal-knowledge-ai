from __future__ import annotations
import uuid
from collections.abc import Iterator
from fastapi import Depends, Header, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.core.config import settings
from app.db.models import AccessGrant, Organization
from app.db.session import get_db, get_tenant_db
from app.security.accounts import OrganizationMembership, UserAccount
from app.security.jwt import JWTError, decode_jwt
from app.security.labels import Role, Sensitivity, normalize
from app.security.principal import Principal, owner_principal

def get_or_create_default_org(db: Session) -> Organization:
    org = db.scalars(select(Organization).where(Organization.slug == settings.default_org_slug)).first()
    if org is None:
        org = Organization(slug=settings.default_org_slug, name=settings.default_org_name); db.add(org); db.commit(); db.refresh(org)
    return org

def resolve_principal(db: Session = Depends(get_db), authorization: str | None = Header(default=None)) -> Principal:
    org = get_or_create_default_org(db)
    if not authorization or not authorization.startswith("Bearer "):
        if settings.auth_mode == "owner_dev" and settings.environment.lower() != "production": return owner_principal(org.id)
        raise HTTPException(401, "authentication required: sign in first", headers={"WWW-Authenticate": "Bearer"})
    try: payload = decode_jwt(authorization[7:].strip())
    except JWTError as exc: raise HTTPException(401, "invalid or expired session", headers={"WWW-Authenticate": "Bearer"}) from exc
    org_id = _uuid(payload.get("org_id")) or org.id
    user_id = _uuid(payload.get("sub") or payload.get("user_id"))
    membership = db.scalar(select(OrganizationMembership).where(OrganizationMembership.org_id == org_id, OrganizationMembership.user_id == user_id, OrganizationMembership.is_active.is_(True))) if user_id else None
    if settings.environment.lower() == "production" and not membership: raise HTTPException(403, "your account is not a member of this organization")
    role = membership.role if membership else normalize(payload.get("role", Role.VIEWER), Role, Role.VIEWER)
    grants = list(db.scalars(select(AccessGrant).where(AccessGrant.org_id == org_id, AccessGrant.user_id == user_id))) if user_id else []
    if role in (Role.OWNER, Role.ADMIN): return owner_principal(org_id, user_id) if role == Role.OWNER else Principal(org_id=org_id, user_id=user_id, role=role, max_sensitivity=Sensitivity.CUSTOMER_DATA, allow_vendor_restricted=True, account_refs=None, include_unapproved=True, label="jwt", grants=tuple(str(g.id) for g in grants))
    max_sensitivity = payload.get("max_sensitivity", Sensitivity.INTERNAL.value); accounts: set[str] = set()
    allow_vendor = bool(payload.get("allow_vendor_restricted", False))
    for grant in grants:
        if grant.account_ref: accounts.add(grant.account_ref)
        allow_vendor = allow_vendor or bool(grant.allow_vendor_restricted)
    return Principal(org_id=org_id, user_id=user_id, role=role, max_sensitivity=max_sensitivity, allow_vendor_restricted=allow_vendor, account_refs=frozenset(accounts), include_unapproved=False, label="jwt", grants=tuple(str(g.id) for g in grants))

def _uuid(value: object) -> uuid.UUID | None:
    try: return uuid.UUID(str(value)) if value else None
    except (ValueError, AttributeError, TypeError): return None

def get_db_for_principal(principal: Principal = Depends(resolve_principal)) -> Iterator[Session]: yield from get_tenant_db(principal.org_id)
