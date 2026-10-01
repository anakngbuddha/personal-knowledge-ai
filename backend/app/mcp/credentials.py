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
    try:
        return Fernet(key.encode("ascii")), InvalidToken
    except (ValueError, UnicodeError) as exc:
        raise CredentialError("credential key must be a valid Fernet key") from exc


def encrypt_secret(plaintext: str) -> bytes:
    from app.security.credential_crypto import encrypt
    try:
        return encrypt(settings.mcp_credentials_key, plaintext)
    except Exception as exc:
        raise CredentialError("credential encryption failed") from exc


def decrypt_secret(ciphertext: bytes) -> str:
    from app.security.credential_crypto import decrypt
    try:
        return decrypt(settings.mcp_credentials_key, ciphertext)
    except Exception as exc:
        raise CredentialError("credential decryption failed") from exc


def secret_configured() -> bool:
    try:
        _fernet()
        return True
    except CredentialError:
        return False
