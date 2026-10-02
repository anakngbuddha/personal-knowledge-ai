"""Create extensions, tables, migrations, RLS, and the default organization.

Production runs this with the administrator migration CLI before deployment.
The restricted web process leaves AUTO_MIGRATE=false and only checks RLS posture.
"""

from __future__ import annotations

from sqlalchemy import text

from app.core.config import settings
from app.core.logging import get_logger
from app.db.migrations import reconcile_rls, run_migrations
from app.db.models import Base
from app.db.session import engine, system_session

logger = get_logger(__name__)


def should_bootstrap() -> bool:
    return settings.auto_migrate


def ensure_schema() -> list[str]:
    """Idempotent administrator bootstrap, including repair of recorded RLS drift."""
    if engine.dialect.name == "postgresql":
        logger.info("schema bootstrap: enabling PostgreSQL extensions")
        try:
            with engine.begin() as conn:
                conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
                conn.execute(text("CREATE EXTENSION IF NOT EXISTS pg_trgm"))
        except Exception as exc:  # noqa: BLE001
            raise RuntimeError(
                "Could not enable PostgreSQL extensions (vector, pg_trgm). "
                "On Aiven: Overview → Extensions, enable pgvector, then restart Render."
            ) from exc

    logger.info("schema bootstrap: creating missing tables")
    Base.metadata.create_all(bind=engine)
    logger.info("schema bootstrap: applying recorded migrations")
    ran = run_migrations(engine)
    # Migration history cannot prove the current policies or FORCE flags are intact.
    logger.info("schema bootstrap: reconciling table RLS")
    reconcile_rls(engine)

    logger.info("schema bootstrap: creating default organization and workspace")
    db = system_session()
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
