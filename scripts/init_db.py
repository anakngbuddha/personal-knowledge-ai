"""Create or upgrade the schema: extensions, tables, recorded migrations, indexes.

    cd backend && python ../scripts/init_db.py

Safe to run repeatedly, and safe to run against a database created by the previous
build: `create_all` adds the new tables, then the recorded migrations add the new
columns and indexes to the tables that already existed.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from app.core.config import settings  # noqa: E402
from app.db.migrations import run_migrations  # noqa: E402
from app.db.models import Base  # noqa: E402
from app.db.session import SessionLocal, engine  # noqa: E402


def main() -> None:
    from sqlalchemy import text

    with engine.begin() as conn:
        conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))

    Base.metadata.create_all(bind=engine)
    ran = run_migrations(engine)

    db = SessionLocal()
    try:
        from app.documents.service import get_or_create_default_workspace
        from app.security.deps import get_or_create_default_org

        org = get_or_create_default_org(db)
        workspace = get_or_create_default_workspace(db, org.id)
    finally:
        db.close()

    print(f"embedding dimensions : {settings.gemini_embedding_dimensions}")
    print(f"fts configuration    : {settings.fts_config}")
    print(f"migrations applied   : {', '.join(ran) if ran else '(already up to date)'}")
    print(f"organization         : {org.slug} ({org.id})")
    print(f"workspace            : {workspace.name} ({workspace.id})")


if __name__ == "__main__":
    main()
