"""OIDC ID-token validation. Tests use HS256; production uses the configured client secret."""

from __future__ import annotations

from datetime import timedelta
from typing import Any
from urllib.parse import urlencode

from app.core.config import settings
from app.security.jwt import InvalidTokenError, create_jwt, decode_jwt


def authorization_url(
    *,
    issuer: str,
    client_id: str,
    redirect_uri: str,
    state: str,
    nonce: str,
) -> str:
    base = issuer.rstrip("/") + "/authorize"
    query = urlencode(
        {
            "response_type": "id_token",
            "client_id": client_id,
            "redirect_uri": redirect_uri,
            "scope": "openid profile email",
            "state": state,
            "nonce": nonce,
            "response_mode": "form_post",
        }
    )
    return f"{base}?{query}"


def validate_oidc_id_token(
    token: str,
    *,
    issuer: str,
    audience: str,
    secret: str,
    nonce: str | None = None,
) -> dict[str, Any]:
    if not nonce:
        raise InvalidTokenError("oidc nonce required")
    payload = decode_jwt(token, secret_key=secret)
    if payload.get("iss") != issuer:
        raise InvalidTokenError("oidc issuer mismatch")
    aud = payload.get("aud")
    if aud != audience and not (isinstance(aud, list) and audience in aud):
        raise InvalidTokenError("oidc audience mismatch")
    if nonce is not None and payload.get("nonce") != nonce:
        raise InvalidTokenError("oidc nonce mismatch")
    if not payload.get("sub"):
        raise InvalidTokenError("oidc token missing sub")
    return payload


def mint_oidc_id_token(
    *,
    issuer: str,
    audience: str,
    subject: str,
    secret: str,
    role: str,
    org_id: str | None = None,
    org_slug: str | None = None,
    nonce: str | None = None,
    expires_delta: timedelta | None = None,
) -> str:
    """Mint a signed OIDC ID token. Used by tests and the local fake IdP."""
    claims: dict[str, Any] = {
        "iss": issuer,
        "aud": audience,
        "sub": subject,
        "role": role,
    }
    if org_id:
        claims["org_id"] = org_id
    if org_slug:
        claims["org_slug"] = org_slug
    if nonce:
        claims["nonce"] = nonce
    return create_jwt(claims, secret_key=secret, expires_delta=expires_delta or timedelta(minutes=5))


def env_oidc_configured() -> bool:
    return bool(settings.sso_enabled and settings.oidc_issuer and settings.oidc_client_id)
