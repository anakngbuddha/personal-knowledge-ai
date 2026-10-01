"""Single-use SSO state, shared across workers and bound to the initiating browser."""
import hashlib
import secrets
import time
from sqlalchemy import String, Float, delete, select, func
from sqlalchemy.orm import Mapped, mapped_column
from app.db.models import Base
from app.security.jwt import InvalidTokenError


class SsoTransaction(Base):
    __tablename__ = "sso_transactions"
    state_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    binding_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    protocol: Mapped[str] = mapped_column(String(16), nullable=False)
    nonce: Mapped[str] = mapped_column(String(128), nullable=False)
    verifier: Mapped[str] = mapped_column(String(128), nullable=False)
    expires_at: Mapped[float] = mapped_column(Float, nullable=False, index=True)


def digest(value):
    return hashlib.sha256(value.encode()).hexdigest()


def begin(db, protocol, *, request_id=None):
    now = time.time()
    db.execute(delete(SsoTransaction).where(SsoTransaction.expires_at <= now))
    if db.scalar(select(func.count()).select_from(SsoTransaction)) >= 5000:
        raise InvalidTokenError("SSO capacity exceeded")
    state, binding = secrets.token_urlsafe(32), secrets.token_urlsafe(32)
    row = SsoTransaction(state_hash=digest(state), binding_hash=digest(binding), protocol=protocol,
                         nonce=secrets.token_urlsafe(32), verifier=request_id or secrets.token_urlsafe(48), expires_at=now+300)
    db.add(row)
    db.commit()
    return state, binding, row


def consume(db, state, binding, protocol):
    if not state or not binding:
        raise InvalidTokenError("SSO state required")
    # DELETE RETURNING is atomic: only one concurrent callback can claim state.
    row = db.execute(delete(SsoTransaction).where(
        SsoTransaction.state_hash == digest(state), SsoTransaction.binding_hash == digest(binding),
        SsoTransaction.protocol == protocol, SsoTransaction.expires_at > time.time(),
    ).returning(SsoTransaction.nonce, SsoTransaction.verifier)).first()
    db.commit()
    if row is None:
        raise InvalidTokenError("invalid or expired SSO state")
    return row
