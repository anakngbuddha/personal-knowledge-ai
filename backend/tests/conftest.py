"""Test configuration.

Two rules this file exists to enforce:

* No test may make a network call or need an API key. `EMBEDDING_PROVIDER=fake` and
  `STORAGE_BACKEND=local` are set before the app is imported, because `Settings` is
  cached at import time.
* Tests that genuinely need PostgreSQL are marked `requires_db` and **skip** rather
  than fail when there is no database. They are not optional in CI: the CI job sets
  `DATABASE_URL` to a service container, so a skip locally is a run in CI.
"""

import os
import uuid

os.environ.setdefault("EMBEDDING_PROVIDER", "fake")
os.environ.setdefault("LLM_PROVIDER", "fake")
os.environ.setdefault("STORAGE_BACKEND", "local")
os.environ.setdefault("LOCAL_STORAGE_DIR", "./.test-storage")
os.environ.setdefault("MALWARE_SCANNER", "heuristic")
os.environ.setdefault("OCR_PROVIDER", "none")
os.environ.setdefault("WORKER_ENABLED", "false")
os.environ.setdefault("AUTH_MODE", "owner_dev")

import pytest  # noqa: E402


def pytest_configure(config):
    config.addinivalue_line(
        "markers", "requires_db: needs a live PostgreSQL with pgvector (set DATABASE_URL)"
    )


def _database_reachable() -> bool:
    if not os.environ.get("DATABASE_URL"):
        return False
    try:
        from sqlalchemy import text

        from app.db.session import engine

        with engine.connect() as conn:
            conn.execute(text("select 1"))
        return True
    except Exception:  # noqa: BLE001
        return False


@pytest.fixture(scope="session")
def database():
    if not _database_reachable():
        pytest.skip("no reachable DATABASE_URL; set one to run the integration tests")
    from app.db.migrations import run_migrations
    from app.db.models import Base
    from app.db.session import engine

    Base.metadata.create_all(bind=engine)
    run_migrations(engine)
    return engine


@pytest.fixture
def db(database):
    from app.db.session import SessionLocal

    session = SessionLocal()
    try:
        yield session
    finally:
        session.rollback()
        session.close()


@pytest.fixture
def org_id():
    return uuid.uuid4()
