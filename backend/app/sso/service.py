"""Map validated IdP assertions onto local signed JWTs."""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.errors import AppError
from app.db.models import Organization, SsoProtocol, SsoProvider
from app.security.jwt import mint_token
from app.security.labels import Role, normalize
from app.sso import credentials
from app.sso.oidc import env_oidc_configured, validate_oidc_id_token
from app.sso.saml import parse_saml_assertion


@dataclass(frozen=True)
class SsoConfig:
    protocol: str
    enabled: bool
    issuer: str
    client_id: str | None
    audience: str | None
    secret: str
    org_id: uuid.UUID | None = None


def _user_id(raw: str) -> uuid.UUID:
    try:
        return uuid.UUID(raw)
    except ValueError:
        return uuid.uuid5(uuid.NAMESPACE_URL, raw)


def load_provider(db: Session, org_id: uuid.UUID, protocol: str) -> SsoProvider | None:
    return db.scalar(
        select(SsoProvider).where(SsoProvider.org_id == org_id, SsoProvider.protocol == protocol)
    )


def env_oidc_config() -> SsoConfig | None:
    if not env_oidc_configured():
        return None
    return SsoConfig(
        protocol=SsoProtocol.OIDC,
        enabled=True,
        issuer=settings.oidc_issuer,
        client_id=settings.oidc_client_id,
        audience=settings.oidc_audience or settings.oidc_client_id,
        secret=settings.oidc_client_secret or settings.jwt_secret_key,
    )


def env_saml_config() -> SsoConfig | None:
    if not (settings.sso_enabled and settings.saml_idp_issuer):
        return None
    return SsoConfig(
        protocol=SsoProtocol.SAML,
        enabled=True,
        issuer=settings.saml_idp_issuer,
        client_id=settings.saml_entity_id or None,
        audience=settings.saml_entity_id or settings.saml_acs_url,
        secret=settings.saml_idp_secret or settings.jwt_secret_key,
    )


def provider_to_config(row: SsoProvider) -> SsoConfig:
    secret = ""
    if row.secret_ciphertext:
        secret = credentials.decrypt_secret(row.secret_ciphertext)
    return SsoConfig(
        protocol=row.protocol,
        enabled=row.enabled,
        issuer=row.issuer,
        client_id=row.client_id,
        audience=row.audience or row.client_id,
        secret=secret or settings.jwt_secret_key,
        org_id=row.org_id,
    )


def resolve_config(db: Session, protocol: str, org_id: uuid.UUID | None = None) -> SsoConfig:
    if org_id is not None:
        row = load_provider(db, org_id, protocol)
        if row is not None and row.enabled:
            return provider_to_config(row)
    fallback = env_oidc_config() if protocol == SsoProtocol.OIDC else env_saml_config()
    if fallback is None:
        raise AppError(status_code=404, code="sso_not_configured", message="SSO is not configured")
    return fallback


def resolve_org(db: Session, *, org_id: str | None, org_slug: str | None, fallback: uuid.UUID) -> uuid.UUID:
    if org_id:
        try:
            parsed = uuid.UUID(org_id)
        except ValueError as exc:
            raise AppError(status_code=400, code="invalid_org", message="org_id is not a UUID") from exc
        org = db.get(Organization, parsed)
        if org is None:
            raise AppError(status_code=401, code="unknown_org", message="organization is not registered")
        return org.id
    if org_slug:
        org = db.scalar(select(Organization).where(Organization.slug == org_slug))
        if org is None:
            raise AppError(status_code=401, code="unknown_org", message="organization is not registered")
        return org.id
    return fallback


def issue_local_token(
    *,
    db: Session,
    org_id: uuid.UUID,
    subject: str,
    role: str,
    verified_email: str | None = None,
) -> dict:
    from app.security.accounts import OrganizationMembership, UserAccount
    from app.db.session import scope_session_to_org
    scope_session_to_org(db, org_id)
    user_id = _user_id(subject)
    if verified_email:
        from app.security.accounts import normalize_email
        account = db.scalar(select(UserAccount).where(UserAccount.email == normalize_email(verified_email), UserAccount.is_active.is_(True)))
        if account is None:
            raise AppError("SSO account has no active membership", status_code=403)
        user_id = account.id
    membership = db.scalar(select(OrganizationMembership).join(UserAccount, UserAccount.id == OrganizationMembership.user_id).where(
        OrganizationMembership.org_id == org_id, OrganizationMembership.user_id == user_id,
        OrganizationMembership.is_active.is_(True), UserAccount.is_active.is_(True)))
    if membership is None:
        raise AppError("SSO account has no active membership", status_code=403)
    validated_role = membership.role
    token = mint_token(org_id=org_id, user_id=user_id, role=validated_role)
    return {
        "access_token": token,
        "token_type": "bearer",
        "expires_in_seconds": settings.jwt_access_token_expire_minutes * 60,
        "org_id": str(org_id),
        "user_id": str(user_id),
        "role": validated_role,
        "idp": True,
    }


def exchange_oidc_token(
    db: Session,
    *,
    id_token: str,
    nonce: str | None,
    fallback_org_id: uuid.UUID,
) -> dict:
    config = resolve_config(db, SsoProtocol.OIDC, fallback_org_id)
    payload = validate_oidc_id_token(
        id_token,
        issuer=config.issuer,
        audience=config.audience or config.client_id or "",
        secret=config.secret,
        nonce=nonce,
    )
    org_id = resolve_org(
        db,
        org_id=payload.get("org_id"),
        org_slug=payload.get("org_slug"),
        fallback=config.org_id or fallback_org_id,
    )
    return issue_local_token(
        db=db,
        org_id=org_id,
        subject=str(payload["sub"]),
        role=str(payload.get("role") or Role.VIEWER),
    )


def exchange_saml_assertion(
    db: Session,
    *,
    assertion: str,
    signature: str | None,
    fallback_org_id: uuid.UUID,
) -> dict:
    config = resolve_config(db, SsoProtocol.SAML, fallback_org_id)
    parsed = parse_saml_assertion(
        assertion,
        expected_issuer=config.issuer,
        expected_audience=config.audience,
        secret=config.secret,
        signature=signature,
        allow_unsigned=settings.saml_allow_unsigned,
    )
    org_id = resolve_org(
        db,
        org_id=parsed.org_id,
        org_slug=parsed.org_slug,
        fallback=config.org_id or fallback_org_id,
    )
    return issue_local_token(db=db, org_id=org_id, subject=parsed.name_id, role=parsed.role)
