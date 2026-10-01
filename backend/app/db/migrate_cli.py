"""Run schema migrations with an administrator DATABASE_URL before app deployment.

The web service connects with a restricted NOBYPASSRLS role and never performs DDL.
"""

import argparse

from sqlalchemy import text
from sqlalchemy.engine import Engine

from app.db.bootstrap import ensure_schema
from app.db.session import engine


def grant_runtime_access(db_engine: Engine, role_name: str) -> None:
    """Grant an existing restricted login access using the migration connection.

    Create the service user and password in Aiven first. This command neither
    creates credentials nor changes role attributes or table ownership.
    """
    if db_engine.dialect.name != "postgresql":
        raise RuntimeError("Runtime role grants require PostgreSQL")
    with db_engine.begin() as conn:
        role = conn.execute(
            text("SELECT rolsuper, rolbypassrls, rolcanlogin FROM pg_roles WHERE rolname = :role"),
            {"role": role_name},
        ).one_or_none()
        if role is None:
            raise RuntimeError(f"Create the Aiven service user {role_name!r} before granting access")
        if role[0] or role[1] or not role[2]:
            raise RuntimeError("Runtime role must be a NOSUPERUSER NOBYPASSRLS login")
        database, schema = conn.execute(text("SELECT current_database(), current_schema()")).one()
        if not schema:
            raise RuntimeError("Migration connection has no current schema")
        # SQL identifiers cannot be bind parameters; quote them with the dialect.
        quote = db_engine.dialect.identifier_preparer.quote_identifier
        target, db_name, schema_name = quote(role_name), quote(database), quote(schema)
        statements = (
            f"GRANT CONNECT ON DATABASE {db_name} TO {target}",
            f"GRANT USAGE ON SCHEMA {schema_name} TO {target}",
            f"GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA {schema_name} TO {target}",
            f"GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA {schema_name} TO {target}",
            f"ALTER DEFAULT PRIVILEGES IN SCHEMA {schema_name} "
            f"GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO {target}",
            f"ALTER DEFAULT PRIVILEGES IN SCHEMA {schema_name} "
            f"GRANT USAGE, SELECT ON SEQUENCES TO {target}",
        )
        for statement in statements:
            conn.execute(text(statement))


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--grant-runtime-role", metavar="ROLE",
        help="After migrations, grant access to an existing restricted Aiven service user",
    )
    args = parser.parse_args(argv)
    ensure_schema()
    if args.grant_runtime_role:
        grant_runtime_access(engine, args.grant_runtime_role)
        print("Runtime grants ready. Set Render DATABASE_URL to the restricted user's connection.")


if __name__ == "__main__":
    main()
