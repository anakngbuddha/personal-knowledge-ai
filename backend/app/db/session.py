"""Database engine, sessions, and tenant scoping for PostgreSQL row-level security.

Every PostgreSQL transaction starts by stamping two transaction-local settings that
the ``tenant_isolation`` policies (migration ``0022_row_level_security``) read:

* ``app.current_org_id``: the organization a tenant-scoped session may see.
* ``app.rls_bypass``: ``on`` only for system sessions (workers, boot tasks, scripts).

A session becomes tenant-scoped with :func:`scope_session_to_org`. ``resolve_principal``
calls it for every authenticated request, and because FastAPI caches ``Depends(get_db)``
per request, the route's own ``db`` is the same, now scoped, session.

Unscoped sessions deny tenant rows by default. Trusted boot and worker code must
declare itself a system session with :func:`system_session`.

The settings are applied with ``set_config(..., true)`` in ``after_begin``, so they are
re-applied after every ``commit()`` and never leak to the next user of a pooled
connection (the old ``SET LOCAL`` helper lost its scope at the first commit).
"""

from __future__ import annotations

import uuid
from collections.abc import Iterator
from contextlib import contextmanager

from sqlalchemy import create_engine, event, text
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import settings

# Pooling is sized for one web process plus one ingestion worker thread. Aiven's
# free tier caps connections low, so this stays deliberately small.
engine = create_engine(
    settings.database_url,
    pool_pre_ping=True,
    pool_size=5,
    max_overflow=5,
    pool_recycle=1800,
    future=True,
)
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)

ORG_KEY = "org_id"
BYPASS_KEY = "rls_bypass"

_SCOPE_SQL = text(
    "SELECT set_config('app.current_org_id', :org_id, true), "
    "set_config('app.rls_bypass', :bypass, true)"
)


def _default_bypass() -> bool:
    return not bool(getattr(settings, "rls_default_deny", False))


def _scope_params(info: dict) -> dict[str, str]:
    org_id = info.get(ORG_KEY)
    if org_id:
        return {"org_id": str(org_id), "bypass": "off"}
    bypass = bool(info.get(BYPASS_KEY, _default_bypass()))
    return {"org_id": "", "bypass": "on" if bypass else "off"}


@event.listens_for(Session, "after_begin")
def _apply_tenant_scope(session, transaction, connection) -> None:  # noqa: ARG001
    if connection.dialect.name != "postgresql":
        return
    connection.execute(_SCOPE_SQL, _scope_params(session.info))


def _is_postgres(db: Session) -> bool:
    try:
        return db.get_bind().dialect.name == "postgresql"
    except Exception:  # noqa: BLE001 - unbound or mocked sessions
        return False


def scope_session_to_org(db: Session, org_id: uuid.UUID | str | None) -> None:
    """Restrict every later statement on ``db`` to ``org_id`` under RLS."""
    if org_id is None or not isinstance(db, Session):
        return
    db.info[ORG_KEY] = str(org_id)
    db.info.pop(BYPASS_KEY, None)
    # The current transaction already ran after_begin; re-stamp it now.
    if db.in_transaction() and _is_postgres(db):
        db.execute(_SCOPE_SQL, _scope_params(db.info))


def mark_system_session(db: Session) -> Session:
    """Declare a session as trusted system code (workers, boot tasks)."""
    db.info.pop(ORG_KEY, None)
    db.info[BYPASS_KEY] = True
    if db.in_transaction() and _is_postgres(db):
        db.execute(_SCOPE_SQL, _scope_params(db.info))
    return db


def system_session() -> Session:
    db = SessionLocal()
    db.info[BYPASS_KEY] = True
    return db


@contextmanager
def verified_identity_lookup(db: Session):
    """Trusted pre-tenant lookup, used only after successful password verification."""
    previous = dict(db.info)
    mark_system_session(db)
    try:
        yield db
    finally:
        db.info.clear()
        db.info.update(previous)
        if db.in_transaction() and _is_postgres(db):
            db.execute(_SCOPE_SQL, _scope_params(db.info))


def get_db() -> Iterator[Session]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def get_tenant_db(org_id: uuid.UUID | str | None = None) -> Iterator[Session]:
    """Yield a database session with PostgreSQL row-level security scoped to org_id."""
    db = SessionLocal()
    if org_id:
        db.info[ORG_KEY] = str(org_id)
    else:
        # A tenant session without a tenant must see nothing, never everything.
        db.info[BYPASS_KEY] = False
    try:
        yield db
    finally:
        db.close()
