"""Fernet encrypt/decrypt for tenant MCP secrets. Never log plaintext."""

from __future__ import annotations

import base64
import hashlib

from app.core.config import settings
from app.core.errors import AppError


class CredentialError(AppError):
    def __init__(self, message: str) -> None:
        super().__init__(message, status_code=500, code="mcp_credentials")


def _fernet():
    from cryptography.fernet import Fernet, InvalidToken

    key = (settings.mcp_credentials_key or "").strip()
    if not key:
        raise CredentialError("MCP_CREDENTIALS_KEY is not configured")
    try:
        return Fernet(key.encode("ascii")), InvalidToken
    except (ValueError, Exception):
        digest = hashlib.sha256(key.encode("utf-8")).digest()
        return Fernet(base64.urlsafe_b64encode(digest)), InvalidToken


def encrypt_secret(plaintext: str) -> bytes:
    """Encrypt a tenant secret. Raises if the key is missing."""
    fernet, _ = _fernet()
    return fernet.encrypt(plaintext.encode("utf-8"))


def decrypt_secret(ciphertext: bytes) -> str:
    """Decrypt a tenant secret. Raises if the key is missing or the blob is corrupt."""
    if not ciphertext:
        raise CredentialError("missing ciphertext")
    fernet, invalid = _fernet()
    try:
        return fernet.decrypt(bytes(ciphertext)).decode("utf-8")
    except invalid as exc:
        raise CredentialError("could not decrypt MCP secret") from exc


def secret_configured() -> bool:
    return bool((settings.mcp_credentials_key or "").strip())
