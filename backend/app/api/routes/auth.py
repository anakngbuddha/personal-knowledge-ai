"""Authentication and principal inspection routes for Phase 0."""

from __future__ import annotations

import uuid
from typing import Any

from fastapi import APIRouter, Depends, Header, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.errors import AppError
from app.db.session import get_db
from app.security.deps import get_or_create_default_org, resolve_principal
from app.security.jwt import InvalidTokenError, mint_token
from app.security.labels import Role, normalize
from app.security.principal import Principal
from app.sso.oidc import authorization_url
from app.sso.service import exchange_oidc_token, exchange_saml_assertion

router = APIRouter(prefix="/auth", tags=["auth"])


class TokenRequest(BaseModel):
    org_id: str | None = None
    user_id: str | None = None
    role: str = Role.SOLUTIONS_ENGINEER


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in_seconds: int
    org_id: str
    user_id: str | None
    role: str


@router.post("/token", response_model=TokenResponse)
def issue_token(
    payload: TokenRequest,
    db: Session = Depends(get_db),
) -> TokenResponse:
    """Issue a signed cryptographic JWT for API access."""
    if payload.org_id:
        target_org_id = uuid.UUID(payload.org_id)
    else:
        default_org = get_or_create_default_org(db)
        target_org_id = default_org.id
    target_user_id = uuid.UUID(payload.user_id) if payload.user_id else None

    try:
        validated_role = normalize(payload.role, Role, Role.VIEWER)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc

    token = mint_token(
        org_id=target_org_id,
        user_id=target_user_id,
        role=validated_role,
    )

    return TokenResponse(
        access_token=token,
        token_type="bearer",
        expires_in_seconds=settings.jwt_access_token_expire_minutes * 60,
        org_id=str(target_org_id),
        user_id=str(target_user_id) if target_user_id else None,
        role=validated_role,
    )


@router.get("/me")
def get_current_principal_profile(
    principal: Principal = Depends(resolve_principal),
) -> dict[str, Any]:
    """Inspect the authenticated principal, tenant context, and role capabilities."""
    info = principal.describe()
    info.update(
        {
            "is_owner": principal.is_owner,
            "is_admin": principal.is_admin,
            "can_write_catalog": principal.can_write_catalog,
            "can_manage_users": principal.can_manage_users,
            "can_export_restricted": principal.can_export_restricted,
            "readable_sensitivities": principal.readable_sensitivities(),
        }
    )
    return info


class OidcStartOut(BaseModel):
    authorization_url: str
    state: str
    nonce: str
    redirect_uri: str


class OidcCallbackIn(BaseModel):
    id_token: str
    nonce: str | None = None


class SamlAcsIn(BaseModel):
    SAMLResponse: str
    signature: str | None = None


@router.get("/oidc/start", response_model=OidcStartOut)
def start_oidc() -> OidcStartOut:
    if not (settings.sso_enabled and settings.oidc_issuer and settings.oidc_client_id):
        raise HTTPException(status_code=404, detail="OIDC is not configured")
    import secrets

    state = secrets.token_urlsafe(16)
    nonce = secrets.token_urlsafe(16)
    return OidcStartOut(
        authorization_url=authorization_url(
            issuer=settings.oidc_issuer,
            client_id=settings.oidc_client_id,
            redirect_uri=settings.oidc_redirect_uri,
            state=state,
            nonce=nonce,
        ),
        state=state,
        nonce=nonce,
        redirect_uri=settings.oidc_redirect_uri,
    )


@router.post("/oidc/callback")
def oidc_callback(
    payload: OidcCallbackIn,
    db: Session = Depends(get_db),
) -> dict:
    org = get_or_create_default_org(db)
    try:
        return exchange_oidc_token(
            db,
            id_token=payload.id_token,
            nonce=payload.nonce,
            fallback_org_id=org.id,
        )
    except InvalidTokenError as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc
    except AppError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message) from exc


@router.post("/saml/acs")
def saml_acs(
    payload: SamlAcsIn,
    db: Session = Depends(get_db),
    x_saml_signature: str | None = Header(default=None, alias="X-SAML-Signature"),
) -> dict:
    org = get_or_create_default_org(db)
    try:
        return exchange_saml_assertion(
            db,
            assertion=payload.SAMLResponse,
            signature=payload.signature or x_saml_signature,
            fallback_org_id=org.id,
        )
    except InvalidTokenError as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc
    except AppError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message) from exc
