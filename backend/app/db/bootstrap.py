"""Create extensions, tables, migrations, and the default org on process start.

Render (and any fresh Aiven database) has no schema until this runs. The workflow
worker otherwise UPDATE-s `task_executions` on a table that does not exist.
"""

from __future__ import annotations

from sqlalchemy import text

from app.core.config import settings
from app.core.logging import get_logger
from app.db.migrations import run_migrations
from app.db.models import Base
from app.db.session import SessionLocal, engine

logger = get_logger(__name__)


def should_bootstrap() -> bool:
    if settings.auto_migrate:
        return True
    return settings.environment.lower() in {"production", "prod"}


def ensure_schema() -> list[str]:
    """Idempotent. Safe to call on every boot."""
    if engine.dialect.name == "postgresql":
        try:
            with engine.begin() as conn:
                conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
                conn.execute(text("CREATE EXTENSION IF NOT EXISTS pg_trgm"))
        except Exception as exc:  # noqa: BLE001
            raise RuntimeError(
                "Could not enable PostgreSQL extensions (vector, pg_trgm). "
                "On Aiven: Overview → Extensions, enable pgvector, then restart Render."
            ) from exc

    Base.metadata.create_all(bind=engine)
    ran = run_migrations(engine)

    db = SessionLocal()
    try:
        from app.documents.service import get_or_create_default_workspace
        from app.security.deps import get_or_create_default_org

        org = get_or_create_default_org(db)
        get_or_create_default_workspace(db, org.id)
    finally:
        db.close()

    logger.info(
        "schema ready; migrations applied this boot: %s",
        ", ".join(ran) if ran else "(already up to date)",
    )
    return ran
