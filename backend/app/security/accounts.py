"""Tenant accounts, memberships, and password authentication."""
from __future__ import annotations

import hashlib
import secrets
import threading
import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.config import settings
from app.db.models import Base

_SCHEME = "pbkdf2_sha256"
# Hashes stored with more rounds than this are rejected rather than computed, so a
# tampered row cannot pin a CPU core.
_MAX_ROUNDS = 5_000_000


class UserAccount(Base):
    __tablename__ = "user_accounts"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    email: Mapped[str] = mapped_column(String(320), nullable=False, unique=True, index=True)
    display_name: Mapped[str] = mapped_column(String(255), nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class OrganizationMembership(Base):
    __tablename__ = "organization_memberships"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    org_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("user_accounts.id", ondelete="CASCADE"), nullable=False, index=True)
    role: Mapped[str] = mapped_column(String(32), nullable=False, default="viewer")
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (UniqueConstraint("org_id", "user_id", name="uq_membership_org_user"),)


def normalize_email(email: str) -> str:
    return email.strip().lower()


def _iterations() -> int:
    return int(settings.password_pbkdf2_iterations)


def hash_password(password: str) -> str:
    if len(password) < 10:
        raise ValueError("password must be at least 10 characters")
    rounds = _iterations()
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, rounds)
    return f"{_SCHEME}${rounds}${salt.hex()}${digest.hex()}"


def verify_password(password: str, encoded: str) -> bool:
    try:
        scheme, rounds, salt_hex, digest_hex = encoded.split("$", 3)
        if scheme != _SCHEME:
            return False
        rounds_int = int(rounds)
        if rounds_int <= 0 or rounds_int > _MAX_ROUNDS:
            return False
        digest = hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(salt_hex), rounds_int)
        return secrets.compare_digest(digest.hex(), digest_hex)
    except (TypeError, ValueError, AttributeError):
        return False


def needs_rehash(encoded: str) -> bool:
    """True when a stored hash uses fewer rounds than the current work factor."""
    try:
        scheme, rounds, _, _ = encoded.split("$", 3)
        return scheme != _SCHEME or int(rounds) < _iterations()
    except (TypeError, ValueError, AttributeError):
        return True


_dummy_lock = threading.Lock()
_dummy_hash: str | None = None


def burn_password_check(password: str) -> None:
    """Spend the same work as a real verification when no account matched.

    Without this, an unknown email answers ~instantly while a known one pays the
    PBKDF2 cost, and the response time reveals which emails have accounts.
    """
    global _dummy_hash
    if _dummy_hash is None or not _dummy_hash.split("$", 2)[1] == str(_iterations()):
        with _dummy_lock:
            if _dummy_hash is None or not _dummy_hash.split("$", 2)[1] == str(_iterations()):
                _dummy_hash = hash_password(secrets.token_urlsafe(24))
    verify_password(password, _dummy_hash)
