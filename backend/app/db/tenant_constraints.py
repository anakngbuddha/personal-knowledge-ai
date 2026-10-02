"""Database guards reject inconsistent tenant and workspace foreign-key relationships."""
import time

from sqlalchemy import inspect, text
from sqlalchemy.exc import DBAPIError

from app.core.logging import get_logger

logger = get_logger(__name__)
_LOCK_TIMEOUT = "5s"
_STATEMENT_TIMEOUT = "30s"
_MAX_ATTEMPTS = 5
_RETRYABLE_STATES = {"40P01", "55P03"}

_GUARD = """
CREATE OR REPLACE FUNCTION verify_tenant_parent() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE child jsonb := to_jsonb(NEW); parent jsonb;
BEGIN
  IF child->>TG_ARGV[1] IS NULL THEN RETURN NEW; END IF;
  EXECUTE format('SELECT to_jsonb(p) FROM %I.%I p WHERE p.%I::text = $1',
                 TG_TABLE_SCHEMA, TG_ARGV[0], TG_ARGV[2])
    INTO parent USING child->>TG_ARGV[1];
  IF parent IS NULL OR (child->>'org_id') IS DISTINCT FROM (parent->>'org_id') THEN
    RAISE EXCEPTION 'tenant parent mismatch' USING ERRCODE = '23514';
  END IF;
  IF child ? 'workspace_id' AND parent ? 'workspace_id'
     AND (child->>'workspace_id') IS DISTINCT FROM (parent->>'workspace_id') THEN
    RAISE EXCEPTION 'workspace parent mismatch' USING ERRCODE = '23514';
  END IF;
  RETURN NEW;
END $$
"""

_IMMUTABLE_TENANT = """
CREATE OR REPLACE FUNCTION reject_tenant_move() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  IF OLD.org_id IS DISTINCT FROM NEW.org_id THEN
    RAISE EXCEPTION 'tenant reassignment is prohibited' USING ERRCODE = '23514';
  END IF;
  RETURN NEW;
END $$
"""


def _apply_guard_statements(engine, statements: list[str], label: str) -> None:
    """Commit a guard group atomically, with bounded waits for active tables."""
    logger.info("installing tenant guards: %s", label)
    for attempt in range(_MAX_ATTEMPTS):
        try:
            with engine.begin() as conn:
                conn.execute(text(
                    "SELECT set_config('lock_timeout', :lock_timeout, true), "
                    "set_config('statement_timeout', :statement_timeout, true)"
                ), {"lock_timeout": _LOCK_TIMEOUT, "statement_timeout": _STATEMENT_TIMEOUT})
                conn.execute(text("SELECT pg_advisory_xact_lock(17291, 22)"))
                for statement in statements:
                    conn.execute(text(statement))
            logger.info("tenant guards ready: %s", label)
            return
        except DBAPIError as exc:
            state = getattr(exc.orig, "sqlstate", None)
            if state not in _RETRYABLE_STATES:
                raise
            if attempt == _MAX_ATTEMPTS - 1:
                raise RuntimeError(
                    f"Tenant guard migration blocked for {label} after {_MAX_ATTEMPTS} attempts "
                    f"(SQLSTATE {state}). Check pg_stat_activity and pg_blocking_pids() for "
                    "the blocking transaction, resolve it, then rerun the administrator migration."
                ) from exc
            delay = min(2 ** attempt, 8)
            logger.warning(
                "tenant guard migration waiting for %s (%s), attempt %s/%s; retrying in %ss",
                label, state, attempt + 1, _MAX_ATTEMPTS, delay,
            )
            time.sleep(delay)


def apply_parent_guards(engine):
    inspector = inspect(engine)
    tables = inspector.get_table_names()
    columns = {name: {column["name"] for column in inspector.get_columns(name)} for name in tables}
    quote = engine.dialect.identifier_preparer.quote_identifier
    _apply_guard_statements(engine, [_GUARD, _IMMUTABLE_TENANT], "trigger functions")
    for table in tables:
        if "org_id" not in columns[table]:
            continue
        statements = [
            f"DROP TRIGGER IF EXISTS tenant_immutable ON {quote(table)}",
            f"CREATE TRIGGER tenant_immutable BEFORE UPDATE OF org_id ON {quote(table)} FOR EACH ROW EXECUTE FUNCTION reject_tenant_move()",
        ]
        for fk in inspector.get_foreign_keys(table):
            parent = fk["referred_table"]
            if "org_id" not in columns.get(parent, set()) or len(fk["constrained_columns"]) != 1:
                continue
            column = fk["constrained_columns"][0]
            parent_column = fk["referred_columns"][0]
            trigger = "tenant_parent_" + column
            # Catalog identifiers are quoted separately; literal arguments are escaped.
            args = ", ".join("'" + value.replace("'", "''") + "'" for value in (parent, column, parent_column))
            statements.extend([
                f"DROP TRIGGER IF EXISTS {quote(trigger)} ON {quote(table)}",
                f"CREATE TRIGGER {quote(trigger)} BEFORE INSERT OR UPDATE ON {quote(table)} FOR EACH ROW EXECUTE FUNCTION verify_tenant_parent({args})",
            ])
        _apply_guard_statements(engine, statements, quote(table))
