"""Idempotent schema migrations.

A fresh database is built by ``Base.metadata.create_all``; this list only exists to move
an already-deployed database forward. Entries are ``(name, statements)`` or
``(name, statements, postgres_only)``. A postgres-only entry is recorded as applied on
other dialects without running, because ``create_all`` has already produced the columns
there and ``ADD COLUMN IF NOT EXISTS`` is not portable.
"""
from __future__ import annotations
from sqlalchemy import text
from sqlalchemy.engine import Engine
from app.core.logging import get_logger
logger=get_logger(__name__)

_RBAC=[
 "CREATE TABLE IF NOT EXISTS user_accounts (id uuid PRIMARY KEY DEFAULT gen_random_uuid(), email varchar(320) NOT NULL UNIQUE, display_name varchar(255) NOT NULL, password_hash varchar(255) NOT NULL, is_active boolean NOT NULL DEFAULT true, created_at timestamptz NOT NULL DEFAULT now())",
 "CREATE TABLE IF NOT EXISTS organization_memberships (id uuid PRIMARY KEY DEFAULT gen_random_uuid(), org_id uuid NOT NULL REFERENCES organizations(id) ON DELETE CASCADE, user_id uuid NOT NULL REFERENCES user_accounts(id) ON DELETE CASCADE, role varchar(32) NOT NULL DEFAULT 'viewer', is_active boolean NOT NULL DEFAULT true, created_at timestamptz NOT NULL DEFAULT now(), CONSTRAINT uq_membership_org_user UNIQUE (org_id,user_id))",
 "CREATE INDEX IF NOT EXISTS ix_user_accounts_email ON user_accounts(email)",
 "CREATE INDEX IF NOT EXISTS ix_memberships_org_id ON organization_memberships(org_id)",
 "CREATE INDEX IF NOT EXISTS ix_memberships_user_id ON organization_memberships(user_id)",
]

_UNDERSTANDING=[
 "ALTER TABLE documents ADD COLUMN IF NOT EXISTS summary text",
 "ALTER TABLE documents ADD COLUMN IF NOT EXISTS key_facts jsonb",
 "ALTER TABLE documents ADD COLUMN IF NOT EXISTS topic_tags jsonb",
 "ALTER TABLE documents ADD COLUMN IF NOT EXISTS detected_doc_type varchar(64)",
 "ALTER TABLE documents ADD COLUMN IF NOT EXISTS detected_vendors jsonb",
 "ALTER TABLE documents ADD COLUMN IF NOT EXISTS detected_products jsonb",
 "ALTER TABLE documents ADD COLUMN IF NOT EXISTS detected_version_label varchar(128)",
 "ALTER TABLE documents ADD COLUMN IF NOT EXISTS understanding_confidence double precision",
 "ALTER TABLE documents ADD COLUMN IF NOT EXISTS understanding_source varchar(16)",
 "ALTER TABLE documents ADD COLUMN IF NOT EXISTS understood_at timestamptz",
]

MIGRATIONS=[
 ("0015_multi_user_rbac",_RBAC),
 ("0016_document_understanding",_UNDERSTANDING,True),
]

def applied_migrations(engine: Engine)->set[str]:
 with engine.begin() as conn:
  conn.execute(text("CREATE TABLE IF NOT EXISTS schema_migrations (name varchar(128) PRIMARY KEY, applied_at timestamptz NOT NULL DEFAULT now())")); return set(conn.execute(text("SELECT name FROM schema_migrations")).scalars().all())

def _record(conn,name: str)->None:
 conn.execute(text("INSERT INTO schema_migrations (name) VALUES (:name) ON CONFLICT (name) DO NOTHING"),{"name":name})

def run_migrations(engine: Engine)->list[str]:
 done=applied_migrations(engine); ran=[]; is_pg=engine.dialect.name=="postgresql"
 for entry in MIGRATIONS:
  name=entry[0]; statements=entry[1]; postgres_only=bool(entry[2]) if len(entry)>2 else False
  if name in done: continue
  if postgres_only and not is_pg:
   with engine.begin() as conn: _record(conn,name)
   logger.info("migration %s skipped on %s; create_all already covers it",name,engine.dialect.name); continue
  with engine.begin() as conn:
   for statement in statements:
    if not is_pg and "gen_random_uuid()" in statement.lower(): statement=statement.replace("gen_random_uuid()","lower(hex(randomblob(16)))")
    conn.execute(text(statement))
   _record(conn,name)
  ran.append(name)
 return ran
