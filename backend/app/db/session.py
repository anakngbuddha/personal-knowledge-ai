import uuid
from collections.abc import Iterator

from sqlalchemy import create_engine, text
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


def get_db() -> Iterator[Session]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def get_tenant_db(org_id: uuid.UUID | str | None = None) -> Iterator[Session]:
    """Yield a database session with PostgreSQL Row-Level Security scoped to org_id."""
    db = SessionLocal()
    try:
        if org_id and engine.dialect.name == "postgresql":
            db.execute(
                text("SET LOCAL app.current_org_id = :org_id"),
                {"org_id": str(org_id)},
            )
        yield db
    finally:
        db.close()
