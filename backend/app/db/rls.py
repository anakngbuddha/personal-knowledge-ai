"""PostgreSQL row-level security posture.

RLS policies only protect data when the connecting role cannot bypass them. A
superuser or a role with BYPASSRLS ignores every policy, and a table owner ignores
them unless the table is FORCE ROW LEVEL SECURITY. This module checks all three so the
"app authorization -> RLS -> Postgres" chain is verified at boot instead of assumed.
"""

from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.engine import Engine
import re

from app.core.logging import get_logger

logger = get_logger(__name__)

# Identity tables are read before a tenant is known (login, membership lookup).
EXEMPT_TABLES = frozenset(
    {"organizations", "user_accounts", "schema_migrations"}
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
                "WHERE (EXISTS (SELECT 1 FROM information_schema.columns col WHERE col.table_schema = n.nspname AND col.table_name = c.relname AND col.column_name = 'org_id') OR c.relname IN ('messages', 'product_capabilities', 'reference_architecture_products', 'evaluation_questions')) "
                "AND n.nspname = current_schema() AND c.relkind = 'r'"
            )
        ).all()
        policies = conn.execute(text("SELECT c.relname, p.polname, pg_get_expr(p.polqual, p.polrelid), pg_get_expr(p.polwithcheck, p.polrelid) FROM pg_policy p JOIN pg_class c ON c.oid=p.polrelid JOIN pg_namespace n ON n.oid=c.relnamespace WHERE n.nspname=current_schema()" )).all()
    invalid_policies = []
    for name, _, _ in rows:
        if name in EXEMPT_TABLES:
            continue
        table_policies = [row for row in policies if row[0] == name]
        if len(table_policies) != 1 or table_policies[0][1] != "tenant_isolation":
            invalid_policies.append(str(name))
            continue
        for expression in table_policies[0][2:]:
            normalized = " ".join((expression or "").lower().split())
            if name == "evaluation_questions":
                if re.sub(r"::text|[\s()]", "", normalized) != "current_setting'app.rls_bypass',true='on'":
                    invalid_policies.append(str(name))
                continue
            if "app.current_org_id" not in normalized or "org_id" not in normalized or "is null" in normalized or "or true" in normalized:
                invalid_policies.append(str(name))
                break
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
        "invalid_policy_tables": sorted(set(invalid_policies)),
        "enforced": not superuser and not bypassrls and not unprotected and not invalid_policies,
    }


def check_rls_posture(engine: Engine, *, required: bool) -> dict:
    posture = rls_posture(engine)
    if engine.dialect.name != "postgresql" and required:
        raise RuntimeError("required RLS needs PostgreSQL")
    if engine.dialect.name != "postgresql" or posture.get("enforced"):
        return posture
    problems: list[str] = []
    if posture.get("superuser"):
        problems.append(f"role {posture['role']!r} is a superuser")
    if posture.get("bypassrls"):
        problems.append(f"role {posture['role']!r} has BYPASSRLS")
    if posture.get("unprotected_tables"):
        problems.append("tables without ENABLE+FORCE RLS: " + ", ".join(posture["unprotected_tables"]))
    if posture.get("invalid_policy_tables"):
        problems.append("tables with unexpected tenant policies: " + ", ".join(posture["invalid_policy_tables"]))
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
