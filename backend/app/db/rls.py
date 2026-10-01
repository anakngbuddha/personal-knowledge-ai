"""PostgreSQL row-level security posture.

RLS policies only protect data when the connecting role cannot bypass them. A
superuser or a role with BYPASSRLS ignores every policy, and a table owner ignores
them unless the table is FORCE ROW LEVEL SECURITY. This module checks all three so the
"app authorization -> RLS -> Postgres" chain is verified at boot instead of assumed.
"""

from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.engine import Engine

from app.core.logging import get_logger

logger = get_logger(__name__)

# Identity tables are read before a tenant is known (login, membership lookup).
EXEMPT_TABLES = frozenset(
    {"organizations", "organization_memberships", "user_accounts", "schema_migrations"}
)


def rls_posture(engine: Engine) -> dict:
    if engine.dialect.name != "postgresql":
        return {"dialect": engine.dialect.name, "enforced": False, "reason": "not postgresql"}
    with engine.connect() as conn:
        role = conn.execute(
            text(
                "SELECT current_user, rolsuper, rolbypassrls FROM pg_roles "
                "WHERE rolname = current_user"
            )
        ).one()
        rows = conn.execute(
            text(
                "SELECT c.relname, c.relrowsecurity, c.relforcerowsecurity "
                "FROM pg_class c "
                "JOIN pg_namespace n ON n.oid = c.relnamespace "
                "JOIN information_schema.columns col "
                "  ON col.table_schema = n.nspname AND col.table_name = c.relname "
                "  AND col.column_name = 'org_id' "
                "WHERE n.nspname = current_schema() AND c.relkind = 'r'"
            )
        ).all()
    unprotected = sorted(
        str(name) for name, enabled, forced in rows if name not in EXEMPT_TABLES and not (enabled and forced)
    )
    superuser = bool(role[1])
    bypassrls = bool(role[2])
    return {
        "role": str(role[0]),
        "superuser": superuser,
        "bypassrls": bypassrls,
        "unprotected_tables": unprotected,
        "enforced": not superuser and not bypassrls and not unprotected,
    }


def check_rls_posture(engine: Engine, *, required: bool) -> dict:
    posture = rls_posture(engine)
    if engine.dialect.name != "postgresql" or posture.get("enforced"):
        return posture
    problems: list[str] = []
    if posture.get("superuser"):
        problems.append(f"role {posture['role']!r} is a superuser")
    if posture.get("bypassrls"):
        problems.append(f"role {posture['role']!r} has BYPASSRLS")
    if posture.get("unprotected_tables"):
        problems.append("tables without ENABLE+FORCE RLS: " + ", ".join(posture["unprotected_tables"]))
    message = "row-level security is NOT enforced: " + "; ".join(problems)
    if required:
        raise RuntimeError(
            message + ". Use a restricted NOSUPERUSER NOBYPASSRLS login in DATABASE_URL "
            "(not avnadmin). With the administrator connection, run "
            "python -m app.db.migrate_cli --grant-runtime-role pka_app, then set "
            "Render DATABASE_URL to that user's connection and redeploy. "
            "Keep RLS_REQUIRED=true. See docs/rls-and-search-cutover.md."
        )
    logger.error(message)
    return posture
