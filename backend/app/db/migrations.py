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
from app.db.models import ContextKind, CurationStatus, RelationType
logger=get_logger(__name__)

def _in_list(values)->str:
 return ", ".join(f"'{value}'" for value in sorted(values))

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

# 3.2 selling model: the seven selling relations, and use cases / room types /
# platforms as things a product can be sold against.
_SELLING_MODEL=[
 "ALTER TABLE product_edges DROP CONSTRAINT IF EXISTS ck_product_edges_relation_type",
 "ALTER TABLE product_edges ADD CONSTRAINT ck_product_edges_relation_type CHECK (relation_type in ("+_in_list(RelationType.ALL)+"))",
 "ALTER TABLE product_edges ADD COLUMN IF NOT EXISTS page_number integer",
 "ALTER TABLE products ADD COLUMN IF NOT EXISTS curation_status varchar(16) NOT NULL DEFAULT 'confirmed'",
 "ALTER TABLE products ADD COLUMN IF NOT EXISTS is_ai_suggested boolean NOT NULL DEFAULT false",
 "ALTER TABLE products ADD COLUMN IF NOT EXISTS aliases jsonb",
 "ALTER TABLE products ADD COLUMN IF NOT EXISTS source_document_id uuid REFERENCES documents(id) ON DELETE SET NULL",
 "ALTER TABLE products ADD COLUMN IF NOT EXISTS is_demo boolean NOT NULL DEFAULT false",
 "ALTER TABLE products DROP CONSTRAINT IF EXISTS ck_products_curation_status",
 "ALTER TABLE products ADD CONSTRAINT ck_products_curation_status CHECK (curation_status in ("+_in_list(CurationStatus.ALL)+"))",
 "CREATE INDEX IF NOT EXISTS ix_products_curation_status ON products(curation_status)",
 "CREATE INDEX IF NOT EXISTS ix_products_source_document_id ON products(source_document_id)",
 "CREATE TABLE IF NOT EXISTS selling_contexts (id uuid PRIMARY KEY DEFAULT gen_random_uuid(), org_id uuid NOT NULL REFERENCES organizations(id) ON DELETE CASCADE, workspace_id uuid NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE, kind varchar(16) NOT NULL, name varchar(255) NOT NULL, slug varchar(128) NOT NULL, description text, aliases jsonb, curation_status varchar(16) NOT NULL DEFAULT 'confirmed', is_ai_suggested boolean NOT NULL DEFAULT false, source_document_id uuid REFERENCES documents(id) ON DELETE SET NULL, is_demo boolean NOT NULL DEFAULT false, created_at timestamptz NOT NULL DEFAULT now(), updated_at timestamptz NOT NULL DEFAULT now(), CONSTRAINT uq_selling_contexts_workspace_kind_slug UNIQUE (workspace_id,kind,slug), CONSTRAINT ck_selling_contexts_kind CHECK (kind in ("+_in_list(ContextKind.ALL)+")), CONSTRAINT ck_selling_contexts_curation_status CHECK (curation_status in ("+_in_list(CurationStatus.ALL)+")))",
 "CREATE INDEX IF NOT EXISTS ix_selling_contexts_org_id ON selling_contexts(org_id)",
 "CREATE INDEX IF NOT EXISTS ix_selling_contexts_workspace_id ON selling_contexts(workspace_id)",
 "CREATE INDEX IF NOT EXISTS ix_selling_contexts_kind ON selling_contexts(kind)",
 "CREATE TABLE IF NOT EXISTS product_context_links (id uuid PRIMARY KEY DEFAULT gen_random_uuid(), org_id uuid NOT NULL REFERENCES organizations(id) ON DELETE CASCADE, workspace_id uuid NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE, product_id uuid NOT NULL REFERENCES products(id) ON DELETE CASCADE, context_id uuid NOT NULL REFERENCES selling_contexts(id) ON DELETE CASCADE, relation_type varchar(32) NOT NULL DEFAULT 'suits_use_case', evidence text NOT NULL, confidence double precision NOT NULL DEFAULT 1.0, document_id uuid REFERENCES documents(id) ON DELETE SET NULL, page_number integer, is_ai_suggested boolean NOT NULL DEFAULT false, status varchar(32) NOT NULL DEFAULT 'approved', rejection_reason text, created_at timestamptz NOT NULL DEFAULT now(), updated_at timestamptz NOT NULL DEFAULT now(), CONSTRAINT uq_product_context_link UNIQUE (product_id,context_id,relation_type), CONSTRAINT ck_product_context_links_relation_type CHECK (relation_type in ('certified_for', 'requires_license', 'suits_use_case')), CONSTRAINT ck_product_context_links_status CHECK (status in ('approved', 'pending_review', 'rejected')), CONSTRAINT ck_product_context_links_evidence_required CHECK (length(trim(evidence)) > 0))",
 "CREATE INDEX IF NOT EXISTS ix_product_context_links_product_id ON product_context_links(product_id)",
 "CREATE INDEX IF NOT EXISTS ix_product_context_links_context_id ON product_context_links(context_id)",
 "CREATE INDEX IF NOT EXISTS ix_product_context_links_status ON product_context_links(status)",
]

# 3.3 sample material is marked, so retrieval can drop it. Existing rows are real
# uploads by definition, so the default is false and no backfill is needed.
_DEMO_SOURCES=[
 "ALTER TABLE documents ADD COLUMN IF NOT EXISTS is_demo boolean NOT NULL DEFAULT false",
 "CREATE INDEX IF NOT EXISTS ix_documents_is_demo ON documents(is_demo)",
]

MIGRATIONS=[
 ("0015_multi_user_rbac",_RBAC),
 ("0016_document_understanding",_UNDERSTANDING,True),
 ("0017_selling_model",_SELLING_MODEL,True),
 ("0018_demo_sources",_DEMO_SOURCES,True),
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
