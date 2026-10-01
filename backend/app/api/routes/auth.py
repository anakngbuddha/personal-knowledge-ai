from __future__ import annotations

import uuid
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, Form, status
from fastapi.responses import RedirectResponse
from pydantic import ConfigDict
from app.sso.transactions import begin, consume
from app.sso.standards import oidc_url, oidc_exchange, saml_client
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.errors import AppError
from app.db.models import Organization
from app.db.session import get_db, scope_session_to_org, verified_identity_lookup
from app.security.accounts import OrganizationMembership, UserAccount, hash_password, normalize_email, verify_password
from app.security.deps import get_or_create_default_org, resolve_principal
from app.security.jwt import InvalidTokenError, mint_token
from app.security.labels import Role, normalize, role_has_access, role_rank
from app.security.audit import record_audit
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
    scope_session_to_org(db, org.id)
    membership = OrganizationMembership(org_id=org.id, user_id=user.id, role=Role.OWNER)
    db.add(membership); db.commit()
    return _token(user, membership)

@router.post("/login", response_model=TokenResponse)
def login(payload: LoginRequest, db: Session = Depends(get_db)):
    user = db.scalar(select(UserAccount).where(UserAccount.email == normalize_email(payload.email), UserAccount.is_active.is_(True)))
    if not user or not verify_password(payload.password, user.password_hash):
        raise HTTPException(401, "email or password is incorrect")
    # Password verification above is the only entry to this pre-tenant read.
    with verified_identity_lookup(db):
        memberships = list(db.scalars(select(OrganizationMembership).where(OrganizationMembership.user_id == user.id, OrganizationMembership.is_active.is_(True)).order_by(OrganizationMembership.id).limit(100)))
    if payload.organization_slug:
        org = db.scalar(select(Organization).where(Organization.slug == _slug(payload.organization_slug)))
        memberships = [m for m in memberships if org and m.org_id == org.id]
    if not memberships:
        raise HTTPException(403, "your account has no active organization membership")
    scope_session_to_org(db, memberships[0].org_id)
    return _token(user, memberships[0])

@router.post("/token", response_model=TokenResponse)
def issue_token(payload: TokenRequest, db: Session = Depends(get_db)):
    raise HTTPException(410, "use /auth/signup or /auth/login")

@router.get("/me")
def get_current_principal_profile(
    principal: Principal = Depends(resolve_principal),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    info = principal.describe()
    org = db.get(Organization, principal.org_id)
    info.update({
        "organization_name": org.name if org else "",
        "is_owner": principal.is_owner,
        "is_admin": principal.is_admin,
        "can_write_catalog": principal.can_write_catalog,
        "can_manage_users": principal.can_manage_users,
        "can_export_restricted": principal.can_export_restricted,
        "readable_sensitivities": principal.readable_sensitivities(),
    })
    return info

@router.get("/members")
def list_members(limit: int = Query(50, ge=1, le=100), offset: int = Query(0, ge=0, le=10000), principal: Principal = Depends(resolve_principal), db: Session = Depends(get_db)):
    if not principal.can_manage_users: raise HTTPException(403, "admin access required")
    rows = db.execute(select(UserAccount, OrganizationMembership).join(OrganizationMembership, OrganizationMembership.user_id == UserAccount.id).where(OrganizationMembership.org_id == principal.org_id).order_by(UserAccount.id).limit(limit).offset(offset)).all()
    return [{"id": str(u.id), "email": u.email, "display_name": u.display_name, "role": m.role, "is_active": u.is_active and m.is_active} for u, m in rows]

@router.post("/members", status_code=201)
def add_member(payload: MemberCreate, principal: Principal = Depends(resolve_principal), db: Session = Depends(get_db)):
    if not principal.can_manage_users: raise HTTPException(403, "admin access required")
    role = normalize(payload.role, Role, Role.VIEWER)
    if principal.role != Role.OWNER and role_rank(role) >= role_rank(principal.role):
        raise HTTPException(403, "cannot assign a peer or higher role")
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
    if role_has_access(role, Role.OWNER) and principal.role != Role.OWNER: raise HTTPException(403, "only an owner can assign owner")
    # Serialize role changes for this organization to preserve the last-owner invariant.
    db.scalar(select(Organization).where(Organization.id == principal.org_id).with_for_update())
    membership = db.scalar(select(OrganizationMembership).where(OrganizationMembership.org_id == principal.org_id, OrganizationMembership.user_id == user_id).with_for_update())
    if not membership:
        raise HTTPException(404, "member not found")
    if principal.role != Role.OWNER and (role_rank(membership.role) >= role_rank(principal.role) or role_rank(role) >= role_rank(principal.role)):
        raise HTTPException(403, "cannot modify a peer or higher role")
    if user_id == principal.user_id and principal.role != Role.OWNER:
        raise HTTPException(403, "cannot change your own role")
    if membership.role == Role.OWNER and role != Role.OWNER:
        other_owner = db.scalar(select(OrganizationMembership.id).join(UserAccount, UserAccount.id == OrganizationMembership.user_id).where(
            OrganizationMembership.org_id == principal.org_id, OrganizationMembership.role == Role.OWNER,
            OrganizationMembership.is_active.is_(True), UserAccount.is_active.is_(True), OrganizationMembership.user_id != user_id).limit(1))
        if other_owner is None:
            raise HTTPException(409, "organization must retain an active owner")
    previous = membership.role
    membership.role = role
    record_audit(db, principal, "role_change", "membership", str(user_id), {"previous_role": previous, "role": role})
    return {"user_id": str(user_id), "role": role}


class OidcStartOut(BaseModel):
    authorization_url: str
    state: str
    nonce: str
    redirect_uri: str


def _sso_cookie(response, binding, protocol):
    secure = settings.environment.lower() == "production"
    response.set_cookie("pka_sso_" + protocol, binding, max_age=300, httponly=True, secure=secure,
                        samesite="none" if protocol == "saml" and secure else "lax", path="/auth")


@router.get("/oidc/start", response_model=OidcStartOut)
def start_oidc(response: Response, db: Session = Depends(get_db)):
    if not (settings.sso_enabled and settings.oidc_issuer and settings.oidc_client_id):
        raise HTTPException(404, "OIDC is not configured")
    try:
        state, binding, transaction = begin(db, "oidc")
        url = oidc_url(state, transaction.nonce, transaction.verifier)
        _sso_cookie(response, binding, "oidc")
        return OidcStartOut(authorization_url=url, state=state, nonce=transaction.nonce, redirect_uri=settings.oidc_redirect_uri)
    except Exception as exc:
        raise HTTPException(503, "SSO unavailable") from exc


@router.post("/oidc/callback")
def reject_implicit_oidc():
    raise HTTPException(410, "use authorization code callback")


@router.get("/oidc/callback")
def oidc_callback(request: Request, response: Response, code: str = Query(..., min_length=1, max_length=4096),
                  state: str = Query(..., min_length=1, max_length=128), db: Session = Depends(get_db)):
    if not settings.sso_enabled:
        raise HTTPException(404, "SSO unavailable")
    try:
        nonce, verifier = consume(db, state, request.cookies.get("pka_sso_oidc"), "oidc")
        org = get_or_create_default_org(db)
        result = oidc_exchange(db, code, nonce, verifier, org.id)
        response.delete_cookie("pka_sso_oidc", path="/auth")
        return result
    except Exception as exc:
        raise HTTPException(401, "invalid SSO response") from exc


@router.get("/saml/start")
def start_saml(request: Request, db: Session = Depends(get_db)):
    if not settings.sso_enabled:
        raise HTTPException(404, "SSO unavailable")
    try:
        auth = saml_client(request)
        # Toolkit generates an unpredictable AuthnRequest ID for InResponseTo validation.
        auth.login()
        state, binding, transaction = begin(db, "saml", request_id=auth.get_last_request_id())
        url = auth.login(return_to=state)
        # login() generates a fresh ID; persist that exact value.
        transaction.verifier = auth.get_last_request_id()
        db.commit()
        response = RedirectResponse(url)
        _sso_cookie(response, binding, "saml")
        return response
    except Exception as exc:
        raise HTTPException(503, "SSO unavailable") from exc


@router.post("/saml/acs")
def saml_acs(request: Request, response: Response, SAMLResponse: str = Form(..., max_length=262144),
             RelayState: str = Form(..., max_length=128), db: Session = Depends(get_db)):
    if not settings.sso_enabled:
        raise HTTPException(404, "SSO unavailable")
    try:
        _, request_id = consume(db, RelayState, request.cookies.get("pka_sso_saml"), "saml")
        auth = saml_client(request, response=SAMLResponse)
        auth.process_response(request_id=request_id)
        if auth.get_errors() or not auth.is_authenticated():
            raise InvalidTokenError("invalid SAML response")
        org = get_or_create_default_org(db)
        from app.sso.service import issue_local_token
        result = issue_local_token(db=db, org_id=org.id, subject=auth.get_nameid(), role="viewer")
        response.delete_cookie("pka_sso_saml", path="/auth")
        return result
    except Exception as exc:
        raise HTTPException(401, "invalid SSO response") from exc
