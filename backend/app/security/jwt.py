"""Cryptographic JWT authentication utilities.

Zero-dependency standard implementation using Python's stdlib (hmac, hashlib, base64).
Supports HMAC-SHA256 (HS256) signature verification and timestamp validation.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import time
import uuid
from datetime import timedelta
from typing import Any

from app.core.config import settings


class JWTError(Exception):
    """Base exception for JWT failures."""


class TokenExpiredError(JWTError):
    """Token has passed its expiration time."""


class InvalidTokenError(JWTError):
    """Token is malformed or signature verification failed."""


def _base64url_encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _base64url_decode(data: str) -> bytes:
    padding = (4 - len(data) % 4) % 4
    return base64.urlsafe_b64decode((data + "=" * padding).encode("ascii"))


def create_jwt(
    claims: dict[str, Any],
    secret_key: str | None = None,
    expires_delta: timedelta | None = None,
) -> str:
    """Create a signed JWT with HS256."""
    key = (secret_key or settings.jwt_secret_key).encode("utf-8")
    now = int(time.time())

    payload = dict(claims)
    payload.setdefault("iat", now)
    if "exp" not in payload:
        delta = expires_delta or timedelta(minutes=settings.jwt_access_token_expire_minutes)
        payload["exp"] = now + int(delta.total_seconds())

    # Stringify UUIDs for JSON serialization
    for k, v in list(payload.items()):
        if isinstance(v, uuid.UUID):
            payload[k] = str(v)

    header = {"alg": "HS256", "typ": "JWT"}
    encoded_header = _base64url_encode(json.dumps(header, separators=(",", ":")).encode("utf-8"))
    encoded_payload = _base64url_encode(json.dumps(payload, separators=(",", ":")).encode("utf-8"))

    signing_input = f"{encoded_header}.{encoded_payload}".encode("ascii")
    signature = hmac.new(key, signing_input, hashlib.sha256).digest()
    encoded_signature = _base64url_encode(signature)

    return f"{encoded_header}.{encoded_payload}.{encoded_signature}"


def decode_jwt(
    token: str,
    secret_key: str | None = None,
    verify_exp: bool = True,
) -> dict[str, Any]:
    """Verify and decode an HS256 JWT token."""
    key = (secret_key or settings.jwt_secret_key).encode("utf-8")
    parts = token.strip().split(".")
    if len(parts) != 3:
        raise InvalidTokenError("token must contain exactly 3 dot-separated parts")

    header_b64, payload_b64, signature_b64 = parts

    try:
        header_bytes = _base64url_decode(header_b64)
        header = json.loads(header_bytes.decode("utf-8"))
    except Exception as exc:
        raise InvalidTokenError("malformed JWT header") from exc

    if header.get("alg") != "HS256":
        raise InvalidTokenError(f"unsupported JWT algorithm: {header.get('alg')}")

    signing_input = f"{header_b64}.{payload_b64}".encode("ascii")
    expected_sig = hmac.new(key, signing_input, hashlib.sha256).digest()

    try:
        signature = _base64url_decode(signature_b64)
    except Exception as exc:
        raise InvalidTokenError("malformed signature encoding") from exc

    if not hmac.compare_digest(expected_sig, signature):
        raise InvalidTokenError("token signature verification failed")

    try:
        payload_bytes = _base64url_decode(payload_b64)
        payload = json.loads(payload_bytes.decode("utf-8"))
    except Exception as exc:
        raise InvalidTokenError("malformed JWT payload") from exc

    if verify_exp:
        exp = payload.get("exp")
        if exp is not None:
            now = int(time.time())
            if now > exp:
                raise TokenExpiredError("token has expired")

    return payload


def mint_token(
    org_id: uuid.UUID | str,
    user_id: uuid.UUID | str | None = None,
    role: str = "viewer",
    expires_delta: timedelta | None = None,
    extra_claims: dict[str, Any] | None = None,
) -> str:
    """Convenience helper to mint a signed bearer token for a user/principal."""
    claims: dict[str, Any] = {
        "org_id": str(org_id),
        "role": role,
    }
    if user_id:
        claims["sub"] = str(user_id)
    if extra_claims:
        claims.update(extra_claims)

    return create_jwt(claims, expires_delta=expires_delta)
