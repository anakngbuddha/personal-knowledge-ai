
"""Idempotent schema migrations."""
from __future__ import annotations
from sqlalchemy import text
from sqlalchemy.engine import Engine
from app.core.logging import get_logger
logger=get_logger(__name__)
MIGRATIONS=[("0015_multi_user_rbac",["CREATE TABLE IF NOT EXISTS user_accounts (id uuid PRIMARY KEY DEFAULT gen_random_uuid(), email varchar(320) NOT NULL UNIQUE, display_name varchar(255) NOT NULL, password_hash varchar(255) NOT NULL, is_active boolean NOT NULL DEFAULT true, created_at timestamptz NOT NULL DEFAULT now())","CREATE TABLE IF NOT EXISTS organization_memberships (id uuid PRIMARY KEY DEFAULT gen_random_uuid(), org_id uuid NOT NULL REFERENCES organizations(id) ON DELETE CASCADE, user_id uuid NOT NULL REFERENCES user_accounts(id) ON DELETE CASCADE, role varchar(32) NOT NULL DEFAULT 'viewer', is_active boolean NOT NULL DEFAULT true, created_at timestamptz NOT NULL DEFAULT now(), CONSTRAINT uq_membership_org_user UNIQUE (org_id,user_id))","CREATE INDEX IF NOT EXISTS ix_user_accounts_email ON user_accounts(email)","CREATE INDEX IF NOT EXISTS ix_memberships_org_id ON organization_memberships(org_id)","CREATE INDEX IF NOT EXISTS ix_memberships_user_id ON organization_memberships(user_id)"])]

def applied_migrations(engine: Engine)->set[str]:
 with engine.begin() as conn:
  conn.execute(text("CREATE TABLE IF NOT EXISTS schema_migrations (name varchar(128) PRIMARY KEY, applied_at timestamptz NOT NULL DEFAULT now())")); return set(conn.execute(text("SELECT name FROM schema_migrations")).scalars().all())

def run_migrations(engine: Engine)->list[str]:
 done=applied_migrations(engine); ran=[]; is_pg=engine.dialect.name=="postgresql"
 for name, statements in MIGRATIONS:
  if name in done: continue
  with engine.begin() as conn:
   for statement in statements:
    if not is_pg and "gen_random_uuid()" in statement.lower(): statement=statement.replace("gen_random_uuid()","lower(hex(randomblob(16)))")
    conn.execute(text(statement))
   conn.execute(text("INSERT INTO schema_migrations (name) VALUES (:name) ON CONFLICT (name) DO NOTHING"),{"name":name})
  ran.append(name)
 return ran
