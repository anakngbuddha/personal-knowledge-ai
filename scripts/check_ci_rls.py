"""Fail the CI/release gate unless the actual restricted runtime connection enforces RLS."""
import os
from sqlalchemy import create_engine
from app.db.rls import check_rls_posture


def main():
    url = os.environ["RLS_RUNTIME_DATABASE_URL"]
    engine = create_engine(url, pool_pre_ping=True)
    try:
        posture = check_rls_posture(engine, required=True)
        assert posture["enforced"] is True
        print("Restricted runtime RLS posture verified")
    finally:
        engine.dispose()


if __name__ == "__main__":
    main()
