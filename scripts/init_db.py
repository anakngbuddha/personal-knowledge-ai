"""Create the V1 schema: pgvector extension, tables, indexes, default workspace.

    cd backend && python ../scripts/init_db.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from sqlalchemy import text  # noqa: E402

from app.core.config import settings  # noqa: E402
from app.db.models import Base  # noqa: E402
from app.db.session import SessionLocal, engine  # noqa: E402
from app.documents.service import get_or_create_default_workspace  # noqa: E402


def main() -> None:
    with engine.begin() as conn:
        conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
        conn.execute(text("CREATE EXTENSION IF NOT EXISTS pg_trgm"))

    Base.metadata.create_all(bind=engine)

    dim = settings.gemini_embedding_dimensions
    with engine.begin() as conn:
        # HNSW cosine index for pgvector. Safe to run repeatedly.
        conn.execute(
            text(
                "CREATE INDEX IF NOT EXISTS ix_document_chunks_embedding_hnsw "
                "ON document_chunks USING hnsw (embedding vector_cosine_ops)"
            )
        )
    db = SessionLocal()
    try:
        workspace = get_or_create_default_workspace(db)
        print(f"schema ready (embedding dim={dim}); workspace '{workspace.name}' id={workspace.id}")
    finally:
        db.close()


if __name__ == "__main__":
    main()
