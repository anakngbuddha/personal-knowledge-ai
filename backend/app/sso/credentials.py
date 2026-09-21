"""Encrypt SSO client secrets. Reuses Fernet; never logs plaintext."""

from __future__ import annotations

import base64
import hashlib

from app.core.config import settings
from app.core.errors import AppError


class SsoCredentialError(AppError):
    def __init__(self, message: str) -> None:
        super().__init__(message, status_code=500, code="sso_credentials")


def _material() -> str:
    return (
        (settings.sso_credentials_key or "").strip()
        or (settings.mcp_credentials_key or "").strip()
        or settings.jwt_secret_key
    )


def _fernet():
    from cryptography.fernet import Fernet, InvalidToken

    key = _material()
    if not key:
        raise SsoCredentialError("SSO credentials key is not configured")
    try:
        return Fernet(key.encode("ascii")), InvalidToken
    except (ValueError, Exception):
        digest = hashlib.sha256(key.encode("utf-8")).digest()
        return Fernet(base64.urlsafe_b64encode(digest)), InvalidToken


def encrypt_secret(plaintext: str) -> bytes:
    fernet, _ = _fernet()
    return fernet.encrypt(plaintext.encode("utf-8"))


def decrypt_secret(ciphertext: bytes) -> str:
    if not ciphertext:
        raise SsoCredentialError("missing ciphertext")
    fernet, invalid = _fernet()
    try:
        return fernet.decrypt(bytes(ciphertext)).decode("utf-8")
    except invalid as exc:
        raise SsoCredentialError("could not decrypt SSO secret") from exc
