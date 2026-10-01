"""Database guards reject inconsistent tenant and workspace foreign-key relationships."""
from sqlalchemy import inspect, text

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


def apply_parent_guards(engine):
    inspector = inspect(engine)
    tables = inspector.get_table_names()
    columns = {name: {column["name"] for column in inspector.get_columns(name)} for name in tables}
    quote = engine.dialect.identifier_preparer.quote_identifier
    with engine.begin() as conn:
        conn.execute(text(_GUARD))
        conn.execute(text(_IMMUTABLE_TENANT))
    for table in tables:
        if "org_id" not in columns[table]:
            continue
        with engine.begin() as conn:
            conn.execute(text(f"DROP TRIGGER IF EXISTS tenant_immutable ON {quote(table)}"))
            conn.execute(text(f"CREATE TRIGGER tenant_immutable BEFORE UPDATE OF org_id ON {quote(table)} FOR EACH ROW EXECUTE FUNCTION reject_tenant_move()"))
        for fk in inspector.get_foreign_keys(table):
            parent = fk["referred_table"]
            if "org_id" not in columns.get(parent, set()) or len(fk["constrained_columns"]) != 1:
                continue
            column = fk["constrained_columns"][0]
            parent_column = fk["referred_columns"][0]
            trigger = "tenant_parent_" + column
            # Catalog identifiers are quoted separately; literal arguments are escaped.
            args = ", ".join("'" + value.replace("'", "''") + "'" for value in (parent, column, parent_column))
            with engine.begin() as conn:
                conn.execute(text(f"DROP TRIGGER IF EXISTS {quote(trigger)} ON {quote(table)}"))
                conn.execute(text(f"CREATE TRIGGER {quote(trigger)} BEFORE INSERT OR UPDATE ON {quote(table)} FOR EACH ROW EXECUTE FUNCTION verify_tenant_parent({args})"))
