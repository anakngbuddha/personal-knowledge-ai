from __future__ import annotations

import uuid
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.errors import AppError
from app.db.models import Organization
from app.db.session import get_db
from app.security.accounts import OrganizationMembership, UserAccount, hash_password, normalize_email, verify_password
from app.security.deps import get_or_create_default_org, resolve_principal
from app.security.jwt import InvalidTokenError, mint_token
from app.security.labels import Role, normalize, role_has_access
from app.security.principal import Principal
from app.sso.oidc import authorization_url
from app.sso.service import exchange_oidc_token, exchange_saml_assertion

router = APIRouter(prefix="/auth", tags=["auth"])

class AuthCredentials(BaseModel):
    email: str
    password: str = Field(min_length=10)

class SignupRequest(AuthCredentials):
    display_name: str = Field(min_length=1, max_length=255)
    organization_name: str = Field(min_length=1, max_length=255)
    organization_slug: str | None = Field(default=None, max_length=64)

class LoginRequest(AuthCredentials):
    organization_slug: str | None = None

class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in_seconds: int
    org_id: str
    user_id: str
    role: str

class TokenRequest(BaseModel):
    org_id: str | None = None
    user_id: str | None = None
    role: str = Role.SOLUTIONS_ENGINEER

class MemberCreate(BaseModel):
    email: str
    display_name: str = Field(min_length=1, max_length=255)
    password: str = Field(min_length=10)
    role: str = Role.VIEWER

class RoleUpdate(BaseModel):
    role: str


def _token(user: UserAccount, membership: OrganizationMembership) -> TokenResponse:
    token = mint_token(membership.org_id, user.id, membership.role)
    return TokenResponse(access_token=token, expires_in_seconds=settings.jwt_access_token_expire_minutes * 60,
                         org_id=str(membership.org_id), user_id=str(user.id), role=membership.role)


def _slug(value: str) -> str:
    result = "".join(ch.lower() if ch.isalnum() else "-" for ch in value).strip("-")
    return result[:64] or "workspace"

@router.post("/signup", response_model=TokenResponse, status_code=201)
def signup(payload: SignupRequest, db: Session = Depends(get_db)):
    email = normalize_email(payload.email)
    if db.scalar(select(UserAccount).where(UserAccount.email == email)):
        raise HTTPException(409, "an account with that email already exists")
    slug = _slug(payload.organization_slug or payload.organization_name)
    if db.scalar(select(Organization).where(Organization.slug == slug)):
        raise HTTPException(409, "that organization name is already in use")
    org = Organization(slug=slug, name=payload.organization_name.strip())
    user = UserAccount(email=email, display_name=payload.display_name.strip(), password_hash=hash_password(payload.password))
    db.add_all([org, user]); db.flush()
    membership = OrganizationMembership(org_id=org.id, user_id=user.id, role=Role.OWNER)
    db.add(membership); db.commit()
    return _token(user, membership)

@router.post("/login", response_model=TokenResponse)
def login(payload: LoginRequest, db: Session = Depends(get_db)):
    user = db.scalar(select(UserAccount).where(UserAccount.email == normalize_email(payload.email), UserAccount.is_active.is_(True)))
    if not user or not verify_password(payload.password, user.password_hash):
        raise HTTPException(401, "email or password is incorrect")
    memberships = list(db.scalars(select(OrganizationMembership).where(OrganizationMembership.user_id == user.id, OrganizationMembership.is_active.is_(True))))
    if payload.organization_slug:
        org = db.scalar(select(Organization).where(Organization.slug == _slug(payload.organization_slug)))
        memberships = [m for m in memberships if org and m.org_id == org.id]
    if not memberships:
        raise HTTPException(403, "your account has no active organization membership")
    return _token(user, memberships[0])

@router.post("/token", response_model=TokenResponse)
def issue_token(payload: TokenRequest, db: Session = Depends(get_db)):
    if settings.environment.lower() == "production" or not settings.allow_legacy_token_endpoint:
        raise HTTPException(410, "use /auth/signup or /auth/login")
    org = get_or_create_default_org(db)
    target_org_id = uuid.UUID(payload.org_id) if payload.org_id else org.id
    user_id = uuid.UUID(payload.user_id) if payload.user_id else uuid.uuid4()
    role = normalize(payload.role, Role, Role.VIEWER)
    return TokenResponse(access_token=mint_token(target_org_id, user_id, role), expires_in_seconds=settings.jwt_access_token_expire_minutes * 60,
                         org_id=str(target_org_id), user_id=str(user_id), role=role)

@router.get("/me")
def get_current_principal_profile(principal: Principal = Depends(resolve_principal)) -> dict[str, Any]:
    info = principal.describe(); info.update({"is_owner": principal.is_owner, "is_admin": principal.is_admin,
        "can_write_catalog": principal.can_write_catalog, "can_manage_users": principal.can_manage_users,
        "can_export_restricted": principal.can_export_restricted, "readable_sensitivities": principal.readable_sensitivities()})
    return info

@router.get("/members")
def list_members(principal: Principal = Depends(resolve_principal), db: Session = Depends(get_db)):
    if not principal.can_manage_users: raise HTTPException(403, "admin access required")
    rows = db.execute(select(UserAccount, OrganizationMembership).join(OrganizationMembership, OrganizationMembership.user_id == UserAccount.id).where(OrganizationMembership.org_id == principal.org_id)).all()
    return [{"id": str(u.id), "email": u.email, "display_name": u.display_name, "role": m.role, "is_active": u.is_active and m.is_active} for u, m in rows]

@router.post("/members", status_code=201)
def add_member(payload: MemberCreate, principal: Principal = Depends(resolve_principal), db: Session = Depends(get_db)):
    if not principal.can_manage_users: raise HTTPException(403, "admin access required")
    role = normalize(payload.role, Role, Role.VIEWER)
    if role_has_access(role, Role.ADMIN) and not principal.is_owner: raise HTTPException(403, "only an owner can add admins")
    email = normalize_email(payload.email)
    user = db.scalar(select(UserAccount).where(UserAccount.email == email))
    if not user:
        user = UserAccount(email=email, display_name=payload.display_name.strip(), password_hash=hash_password(payload.password)); db.add(user); db.flush()
    if db.scalar(select(OrganizationMembership).where(OrganizationMembership.org_id == principal.org_id, OrganizationMembership.user_id == user.id)):
        raise HTTPException(409, "user is already a member")
    membership = OrganizationMembership(org_id=principal.org_id, user_id=user.id, role=role); db.add(membership); db.commit()
    return {"id": str(user.id), "email": user.email, "display_name": user.display_name, "role": role}

@router.patch("/members/{user_id}")
def update_member_role(user_id: uuid.UUID, payload: RoleUpdate, principal: Principal = Depends(resolve_principal), db: Session = Depends(get_db)):
    if not principal.can_manage_users: raise HTTPException(403, "admin access required")
    role = normalize(payload.role, Role, Role.VIEWER)
    if role_has_access(role, Role.OWNER) and not principal.is_owner: raise HTTPException(403, "only an owner can assign owner")
    membership = db.scalar(select(OrganizationMembership).where(OrganizationMembership.org_id == principal.org_id, OrganizationMembership.user_id == user_id))
    if not membership: raise HTTPException(404, "member not found")
    membership.role = role; db.commit(); return {"user_id": str(user_id), "role": role}

class OidcStartOut(BaseModel): authorization_url: str; state: str; nonce: str; redirect_uri: str
class OidcCallbackIn(BaseModel): id_token: str; nonce: str | None = None
class SamlAcsIn(BaseModel): SAMLResponse: str; signature: str | None = None

@router.get("/oidc/start", response_model=OidcStartOut)
def start_oidc() -> OidcStartOut:
    if not (settings.sso_enabled and settings.oidc_issuer and settings.oidc_client_id): raise HTTPException(404, "OIDC is not configured")
    import secrets
    state, nonce = secrets.token_urlsafe(16), secrets.token_urlsafe(16)
    return OidcStartOut(authorization_url=authorization_url(issuer=settings.oidc_issuer, client_id=settings.oidc_client_id, redirect_uri=settings.oidc_redirect_uri, state=state, nonce=nonce), state=state, nonce=nonce, redirect_uri=settings.oidc_redirect_uri)

@router.post("/oidc/callback")
def oidc_callback(payload: OidcCallbackIn, db: Session = Depends(get_db)):
    org = get_or_create_default_org(db)
    try: return exchange_oidc_token(db, id_token=payload.id_token, nonce=payload.nonce, fallback_org_id=org.id)
    except InvalidTokenError as exc: raise HTTPException(401, str(exc)) from exc
    except AppError as exc: raise HTTPException(exc.status_code, exc.message) from exc

@router.post("/saml/acs")
def saml_acs(payload: SamlAcsIn, db: Session = Depends(get_db)):
    org = get_or_create_default_org(db)
    try: return exchange_saml_assertion(db, assertion=payload.SAMLResponse, signature=payload.signature, fallback_org_id=org.id)
    except InvalidTokenError as exc: raise HTTPException(401, str(exc)) from exc
    except AppError as exc: raise HTTPException(exc.status_code, exc.message) from exc
