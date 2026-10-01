"""Verify a transient restricted role in the disposable CI database."""
import os
import secrets
from psycopg import sql
from sqlalchemy import create_engine
from app.db.migrate_cli import grant_runtime_access
from app.db.rls import check_rls_posture
from app.db.session import engine


def main():
    if os.environ.get("CI") != "true":
        raise RuntimeError("This helper is only for the disposable CI database")
    role = "pka_ci_runtime"
    password = secrets.token_urlsafe(32)
    raw = engine.raw_connection()
    try:
        with raw.cursor() as cursor:
            cursor.execute(sql.SQL("CREATE ROLE {} LOGIN NOSUPERUSER NOBYPASSRLS PASSWORD {}").format(sql.Identifier(role), sql.Literal(password)))
        raw.commit()
    finally:
        raw.close()
    grant_runtime_access(engine, role)
    runtime = create_engine(engine.url.set(username=role, password=password))
    try:
        assert check_rls_posture(runtime, required=True)["enforced"] is True
        print("RLS_REQUIRED=true: restricted runtime connection verified")
    finally:
        runtime.dispose()


if __name__ == "__main__":
    main()
