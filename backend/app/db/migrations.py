"""Idempotent schema migrations.

A fresh database is built by ``Base.metadata.create_all``; this list only exists to move
an already-deployed database forward. Entries are ``(name, statements)`` or
``(name, statements, postgres_only)``. A postgres-only entry is recorded as applied on
other dialects without running, because ``create_all`` has already produced the columns
there and ``ADD COLUMN IF NOT EXISTS`` is not portable.
"""
from __future__ import annotations
import time
from sqlalchemy import text
from sqlalchemy.engine import Engine
from sqlalchemy.exc import DBAPIError
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

# 4.4 notebooks: a deal or customer inside the workspace. Sources stay shared;
# the join table is only the on/off switch. Older notes and chats keep a null
# notebook and stay visible at the workspace level.
_NOTEBOOKS=[
 "CREATE TABLE IF NOT EXISTS notebooks (id uuid PRIMARY KEY DEFAULT gen_random_uuid(), org_id uuid NOT NULL REFERENCES organizations(id) ON DELETE CASCADE, workspace_id uuid NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE, name varchar(120) NOT NULL, created_at timestamptz NOT NULL DEFAULT now(), updated_at timestamptz NOT NULL DEFAULT now(), CONSTRAINT uq_notebooks_workspace_name UNIQUE (workspace_id, name))",
 "CREATE INDEX IF NOT EXISTS ix_notebooks_org_id ON notebooks(org_id)",
 "CREATE INDEX IF NOT EXISTS ix_notebooks_workspace_id ON notebooks(workspace_id)",
 "CREATE TABLE IF NOT EXISTS notebook_sources (id uuid PRIMARY KEY DEFAULT gen_random_uuid(), org_id uuid NOT NULL REFERENCES organizations(id) ON DELETE CASCADE, notebook_id uuid NOT NULL REFERENCES notebooks(id) ON DELETE CASCADE, document_id uuid NOT NULL REFERENCES documents(id) ON DELETE CASCADE, enabled boolean NOT NULL DEFAULT true, CONSTRAINT uq_notebook_sources_pair UNIQUE (notebook_id, document_id))",
 "CREATE INDEX IF NOT EXISTS ix_notebook_sources_notebook_id ON notebook_sources(notebook_id)",
 "CREATE INDEX IF NOT EXISTS ix_notebook_sources_document_id ON notebook_sources(document_id)",
 "ALTER TABLE notes ADD COLUMN IF NOT EXISTS notebook_id uuid REFERENCES notebooks(id) ON DELETE SET NULL",
 "ALTER TABLE conversations ADD COLUMN IF NOT EXISTS notebook_id uuid REFERENCES notebooks(id) ON DELETE SET NULL",
 "CREATE INDEX IF NOT EXISTS ix_notes_notebook_id ON notes(notebook_id)",
 "CREATE INDEX IF NOT EXISTS ix_conversations_notebook_id ON conversations(notebook_id)",
]

# Crawl jobs have no document yet, and one vendor source backs many pages.
_VENDOR_CRAWL=[
 "ALTER TABLE ingestion_jobs ALTER COLUMN document_id DROP NOT NULL",
 "ALTER TABLE ingestion_jobs ADD COLUMN IF NOT EXISTS payload jsonb",
 "ALTER TABLE vendor_sources ADD COLUMN IF NOT EXISTS path_prefix text",
 "CREATE TABLE IF NOT EXISTS vendor_source_pages (id uuid PRIMARY KEY DEFAULT gen_random_uuid(), org_id uuid NOT NULL REFERENCES organizations(id) ON DELETE CASCADE, vendor_source_id uuid NOT NULL REFERENCES vendor_sources(id) ON DELETE CASCADE, url text NOT NULL, document_id uuid REFERENCES documents(id) ON DELETE SET NULL, last_hash varchar(64), last_seen_at timestamptz, missing_at timestamptz, created_at timestamptz NOT NULL DEFAULT now(), updated_at timestamptz NOT NULL DEFAULT now(), CONSTRAINT uq_vendor_source_pages_url UNIQUE (vendor_source_id, url))",
 "CREATE INDEX IF NOT EXISTS ix_vendor_source_pages_org_id ON vendor_source_pages(org_id)",
 "CREATE INDEX IF NOT EXISTS ix_vendor_source_pages_vendor_source_id ON vendor_source_pages(vendor_source_id)",
 "CREATE INDEX IF NOT EXISTS ix_vendor_source_pages_document_id ON vendor_source_pages(document_id)",
]

# Cosine HNSW so crawled vendor pages do not force a sequential vector scan.
_VECTOR_HNSW=[
 "CREATE INDEX IF NOT EXISTS ix_document_chunks_embedding_hnsw ON document_chunks USING hnsw (embedding vector_cosine_ops) WITH (m = 16, ef_construction = 64)",
]

# Apply RLS one table per transaction. A single DO block holds AccessExclusiveLock
# on every table until it commits, which deadlocks with the previous Render instance
# during an overlapping deploy. Per-table commits also make retries resumable.
_RLS_TABLES = text("""
    SELECT c.table_schema, c.table_name
    FROM information_schema.columns c
    JOIN information_schema.tables t
      ON t.table_schema = c.table_schema AND t.table_name = c.table_name
    WHERE c.table_schema = current_schema()
      AND c.column_name = 'org_id'
      AND t.table_type = 'BASE TABLE'
      AND c.table_name NOT IN
        ('organizations', 'user_accounts', 'schema_migrations')
    ORDER BY c.table_name
""")
_RLS_READY = text("""
    SELECT c.relrowsecurity AND c.relforcerowsecurity
           AND EXISTS (
               SELECT 1 FROM pg_policy p
               WHERE p.polrelid = c.oid AND p.polname = 'tenant_isolation'
           )
    FROM pg_class c
    JOIN pg_namespace n ON n.oid = c.relnamespace
    WHERE n.nspname = :schema AND c.relname = :table_name
""")
_RLS_PREDICATE = (
    "current_setting('app.rls_bypass', true) = 'on' "
    "OR CAST(org_id AS text) = current_setting('app.current_org_id', true)"
)
_RETRYABLE_DDL_STATES = {"40P01", "55P03"}  # deadlock, lock timeout


def _apply_rls_table(engine: Engine, schema: str, table_name: str) -> None:
    quote = engine.dialect.identifier_preparer.quote_identifier
    table = f"{quote(schema)}.{quote(table_name)}"
    for attempt in range(5):
        try:
            with engine.begin() as conn:
                conn.execute(text("SET LOCAL lock_timeout = '5s'"))
                # Serialize concurrent new instances without holding table locks
                # across tables. The old instance does not use this lock, hence
                # the bounded retry on 40P01/55P03 below.
                conn.execute(text("SELECT pg_advisory_xact_lock(17291, 22)"))
                conn.execute(text(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY"))
                conn.execute(text(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY"))
                conn.execute(text(f"DROP POLICY IF EXISTS tenant_isolation ON {table}"))
                conn.execute(text(
                    f"CREATE POLICY tenant_isolation ON {table} "
                    f"USING ({_RLS_PREDICATE}) WITH CHECK ({_RLS_PREDICATE})"
                ))
            return
        except DBAPIError as exc:
            state = getattr(exc.orig, "sqlstate", None)
            if state not in _RETRYABLE_DDL_STATES or attempt == 4:
                raise
            delay = min(2 ** attempt, 8)
            logger.warning("RLS migration waiting for %s (%s); retrying in %ss", table, state, delay)
            time.sleep(delay)


def _apply_rls(engine: Engine) -> None:
    with engine.connect() as conn:
        tables = conn.execute(_RLS_TABLES).all()
    for schema, table_name in tables:
        _apply_rls_table(engine, schema, table_name)

def _apply_derived_rls(engine):
    predicates = {
        "messages": "EXISTS (SELECT 1 FROM conversations p WHERE p.id = messages.conversation_id AND CAST(p.org_id AS text) = current_setting('app.current_org_id', true))",
        "evaluation_questions": "false",
        "product_capabilities": "EXISTS (SELECT 1 FROM products p JOIN capabilities c ON c.id = product_capabilities.capability_id WHERE p.id = product_capabilities.product_id AND p.org_id = c.org_id AND CAST(p.org_id AS text) = current_setting('app.current_org_id', true))",
        "reference_architecture_products": "EXISTS (SELECT 1 FROM reference_architectures a JOIN products p ON p.id = reference_architecture_products.product_id WHERE a.id = reference_architecture_products.architecture_id AND a.org_id = p.org_id AND a.workspace_id = p.workspace_id AND CAST(a.org_id AS text) = current_setting('app.current_org_id', true))",
    }
    for name, predicate in predicates.items():
        with engine.begin() as conn:
            table = engine.dialect.identifier_preparer.quote_identifier(name)
            conn.execute(text(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY"))
            conn.execute(text(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY"))
            conn.execute(text(f"DROP POLICY IF EXISTS tenant_isolation ON {table}"))
            expression = "current_setting('app.rls_bypass', true) = 'on' OR " + predicate
            if name == "evaluation_questions":
                expression = "current_setting('app.rls_bypass', true) = 'on'"
            conn.execute(text(f"CREATE POLICY tenant_isolation ON {table} USING ({expression}) WITH CHECK ({expression})"))

MIGRATIONS=[
 ("0015_multi_user_rbac",_RBAC),
 ("0016_document_understanding",_UNDERSTANDING,True),
 ("0017_selling_model",_SELLING_MODEL,True),
 ("0018_demo_sources",_DEMO_SOURCES,True),
 ("0019_notebooks",_NOTEBOOKS,True),
 ("0020_vendor_source_pages",_VENDOR_CRAWL,True),
 ("0021_document_chunk_hnsw",_VECTOR_HNSW,True),
 ("0022_row_level_security",[],True),
 ("0023_agent_actions",["""CREATE TABLE IF NOT EXISTS agent_actions (
 id uuid PRIMARY KEY, org_id uuid NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
 workspace_id uuid NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
 user_id uuid, conversation_id uuid REFERENCES conversations(id) ON DELETE SET NULL,
 kind varchar(64) NOT NULL, arguments jsonb NOT NULL, status varchar(16) NOT NULL,
 idempotency_key varchar(128) NOT NULL UNIQUE, result jsonb,
 expires_at timestamptz NOT NULL, created_at timestamptz NOT NULL DEFAULT now(),
 resolved_at timestamptz)
 """, "CREATE INDEX IF NOT EXISTS ix_agent_actions_org_id ON agent_actions(org_id)",
 "CREATE INDEX IF NOT EXISTS ix_agent_actions_workspace_id ON agent_actions(workspace_id)",
 "CREATE INDEX IF NOT EXISTS ix_agent_actions_user_id ON agent_actions(user_id)"],True),
 ("0024_agent_actions_rls",[],True),
 ("0025_sales_foundation",[
  """CREATE TABLE IF NOT EXISTS sales_accounts (
   id uuid PRIMARY KEY, org_id uuid NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
   name varchar(255) NOT NULL, external_system varchar(64), external_id varchar(255),
   created_at timestamptz NOT NULL DEFAULT now(),
   CONSTRAINT uq_sales_account_external UNIQUE (org_id, external_system, external_id))""",
  """CREATE TABLE IF NOT EXISTS opportunities (
   id uuid PRIMARY KEY, org_id uuid NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
   workspace_id uuid NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
   account_id uuid REFERENCES sales_accounts(id) ON DELETE RESTRICT,
   owner_id uuid, title varchar(255) NOT NULL, stage varchar(32) NOT NULL DEFAULT 'discovery',
   currency varchar(3) NOT NULL DEFAULT 'USD', version integer NOT NULL DEFAULT 1,
   created_at timestamptz NOT NULL DEFAULT now(), updated_at timestamptz NOT NULL DEFAULT now(),
   CONSTRAINT ck_opportunity_stage CHECK (stage in ('discovery', 'solution', 'pricing', 'proposal', 'won', 'lost')),
   CONSTRAINT ck_opportunity_version CHECK (version > 0))""",
  """CREATE TABLE IF NOT EXISTS opportunity_requirements (
   id uuid PRIMARY KEY, org_id uuid NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
   opportunity_id uuid NOT NULL REFERENCES opportunities(id) ON DELETE CASCADE,
   source_document_id uuid REFERENCES documents(id) ON DELETE SET NULL,
   original_text text NOT NULL, acceptance_criterion text,
   priority varchar(16) NOT NULL DEFAULT 'must', coverage_state varchar(16) NOT NULL DEFAULT 'unreviewed',
   coverage_note text, reviewer_id uuid, version integer NOT NULL DEFAULT 1,
   created_at timestamptz NOT NULL DEFAULT now(), updated_at timestamptz NOT NULL DEFAULT now(),
   CONSTRAINT ck_requirement_priority CHECK (priority in ('must', 'should', 'could')),
   CONSTRAINT ck_requirement_coverage CHECK (coverage_state in ('unreviewed', 'covered', 'partial', 'gap', 'excluded')),
   CONSTRAINT ck_requirement_version CHECK (version > 0))""",
  "CREATE INDEX IF NOT EXISTS ix_sales_accounts_org_id ON sales_accounts(org_id)",
  "CREATE INDEX IF NOT EXISTS ix_opportunities_org_id ON opportunities(org_id)",
  "CREATE INDEX IF NOT EXISTS ix_opportunities_workspace_id ON opportunities(workspace_id)",
  "CREATE INDEX IF NOT EXISTS ix_opportunities_account_id ON opportunities(account_id)",
  "CREATE INDEX IF NOT EXISTS ix_opportunities_owner_id ON opportunities(owner_id)",
  "CREATE INDEX IF NOT EXISTS ix_opportunities_org_workspace_created ON opportunities(org_id, workspace_id, created_at)",
  "CREATE INDEX IF NOT EXISTS ix_opportunity_requirements_org_id ON opportunity_requirements(org_id)",
  "CREATE INDEX IF NOT EXISTS ix_opportunity_requirements_opportunity_id ON opportunity_requirements(opportunity_id)",
  "CREATE INDEX IF NOT EXISTS ix_requirements_opportunity_priority ON opportunity_requirements(opportunity_id, priority, coverage_state)",
 ],True),
 ("0026_sales_foundation_rls",[],True),
 ("0027_opportunity_participants",[
  """CREATE TABLE IF NOT EXISTS opportunity_participants (
   id uuid PRIMARY KEY, org_id uuid NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
   opportunity_id uuid NOT NULL REFERENCES opportunities(id) ON DELETE CASCADE,
   user_id uuid NOT NULL, access varchar(8) NOT NULL DEFAULT 'read',
   created_at timestamptz NOT NULL DEFAULT now(),
   CONSTRAINT uq_opportunity_participant UNIQUE (opportunity_id, user_id),
   CONSTRAINT ck_opportunity_participant_access CHECK (access in ('read', 'edit')))""",
  "CREATE INDEX IF NOT EXISTS ix_opportunity_participants_org_id ON opportunity_participants(org_id)",
  "CREATE INDEX IF NOT EXISTS ix_opportunity_participants_opportunity_id ON opportunity_participants(opportunity_id)",
  "CREATE INDEX IF NOT EXISTS ix_opportunity_participants_user_id ON opportunity_participants(user_id)",
 ],True),
 ("0028_opportunity_participants_rls",[],True),
 ("0029_sales_commerce",[
  """CREATE TABLE IF NOT EXISTS provider_sku_maps (
   id uuid PRIMARY KEY, org_id uuid NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
   product_id uuid NOT NULL REFERENCES products(id) ON DELETE CASCADE,
   provider varchar(16) NOT NULL, service varchar(128) NOT NULL, sku varchar(255) NOT NULL,
   meter varchar(255), region varchar(128) NOT NULL, billing_mode varchar(64) NOT NULL,
   status varchar(16) NOT NULL DEFAULT 'draft', reviewer_id uuid,
   created_at timestamptz NOT NULL DEFAULT now(),
   CONSTRAINT ck_sku_map_provider CHECK (provider in ('huawei', 'aws', 'azure', 'gcp')),
   CONSTRAINT ck_sku_map_status CHECK (status in ('draft', 'approved', 'retired')))""",
  """CREATE TABLE IF NOT EXISTS price_observations (
   id uuid PRIMARY KEY, org_id uuid NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
   sku_map_id uuid NOT NULL REFERENCES provider_sku_maps(id) ON DELETE RESTRICT,
   payload jsonb NOT NULL, payload_sha256 varchar(64) NOT NULL,
   commercial_cost_per_unit varchar(64) NOT NULL,
   source_kind varchar(16) NOT NULL, created_at timestamptz NOT NULL DEFAULT now())""",
  """CREATE TABLE IF NOT EXISTS commercial_policies (
   id uuid PRIMARY KEY, org_id uuid NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
   payload jsonb NOT NULL, version varchar(64) NOT NULL, created_by uuid,
   created_at timestamptz NOT NULL DEFAULT now(),
   CONSTRAINT uq_commercial_policy_version UNIQUE (org_id, version))""",
  """CREATE TABLE IF NOT EXISTS sales_quotes (
   id uuid PRIMARY KEY, org_id uuid NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
   opportunity_id uuid NOT NULL REFERENCES opportunities(id) ON DELETE RESTRICT,
   created_at timestamptz NOT NULL DEFAULT now())""",
  """CREATE TABLE IF NOT EXISTS sales_quote_versions (
   id uuid PRIMARY KEY, org_id uuid NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
   quote_id uuid NOT NULL REFERENCES sales_quotes(id) ON DELETE RESTRICT,
   number integer NOT NULL, status varchar(16) NOT NULL DEFAULT 'draft',
   policy_id uuid NOT NULL REFERENCES commercial_policies(id) ON DELETE RESTRICT,
   snapshot jsonb NOT NULL, snapshot_sha256 varchar(64) NOT NULL,
   created_by uuid, approved_by uuid, approved_at timestamptz, issued_at timestamptz,
   created_at timestamptz NOT NULL DEFAULT now(),
   CONSTRAINT uq_sales_quote_version UNIQUE (quote_id, number),
   CONSTRAINT ck_sales_quote_status CHECK (status in ('draft', 'review', 'approved', 'issued')),
   CONSTRAINT ck_sales_quote_version_positive CHECK (number > 0))""",
  "CREATE INDEX IF NOT EXISTS ix_provider_sku_maps_org_id ON provider_sku_maps(org_id)",
  "CREATE INDEX IF NOT EXISTS ix_provider_sku_maps_product_id ON provider_sku_maps(product_id)",
  "CREATE INDEX IF NOT EXISTS ix_sku_map_product_region ON provider_sku_maps(org_id, product_id, region)",
  "CREATE INDEX IF NOT EXISTS ix_price_observations_org_id ON price_observations(org_id)",
  "CREATE INDEX IF NOT EXISTS ix_price_observations_sku_map_id ON price_observations(sku_map_id)",
  "CREATE INDEX IF NOT EXISTS ix_commercial_policies_org_id ON commercial_policies(org_id)",
  "CREATE INDEX IF NOT EXISTS ix_sales_quotes_org_id ON sales_quotes(org_id)",
  "CREATE INDEX IF NOT EXISTS ix_sales_quotes_opportunity_id ON sales_quotes(opportunity_id)",
  "CREATE INDEX IF NOT EXISTS ix_sales_quote_versions_org_id ON sales_quote_versions(org_id)",
  "CREATE INDEX IF NOT EXISTS ix_sales_quote_versions_quote_id ON sales_quote_versions(quote_id)",
 ],True),
 ("0030_sales_commerce_rls",[],True),
 ("0031_price_cost_provenance",[
  "ALTER TABLE price_observations ADD COLUMN IF NOT EXISTS commercial_cost_per_unit varchar(64) NOT NULL DEFAULT '0'",
 ],True),
 ("0032_sales_quote_exports",[
  """CREATE TABLE IF NOT EXISTS sales_quote_exports (
   id uuid PRIMARY KEY, org_id uuid NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
   quote_version_id uuid NOT NULL REFERENCES sales_quote_versions(id) ON DELETE RESTRICT,
   destination varchar(32) NOT NULL DEFAULT 'google_sheets',
   status varchar(16) NOT NULL DEFAULT 'pending', external_id varchar(255), created_by uuid,
   created_at timestamptz NOT NULL DEFAULT now(), completed_at timestamptz,
   CONSTRAINT uq_sales_quote_export_destination UNIQUE (quote_version_id, destination),
   CONSTRAINT ck_sales_quote_export_status CHECK (status in ('pending', 'completed', 'needs_reconciliation')))""",
  "CREATE INDEX IF NOT EXISTS ix_sales_quote_exports_org_id ON sales_quote_exports(org_id)",
 ],True),
 ("0033_sales_quote_exports_rls",[],True),
 ("0034_sales_quote_export_retry",[
  "ALTER TABLE sales_quote_exports DROP CONSTRAINT IF EXISTS ck_sales_quote_export_status",
  "ALTER TABLE sales_quote_exports ADD CONSTRAINT ck_sales_quote_export_status CHECK (status in ('pending', 'completed', 'needs_reconciliation', 'retry_authorized'))",
 ],True),
 ("0035_sales_claims",[
  """CREATE TABLE IF NOT EXISTS sales_claims (
   id uuid PRIMARY KEY DEFAULT gen_random_uuid(), org_id uuid NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
   opportunity_id uuid NOT NULL REFERENCES opportunities(id) ON DELETE CASCADE,
   statement text NOT NULL, competitor varchar(255), source_document_id uuid NOT NULL REFERENCES documents(id) ON DELETE RESTRICT,
   source_version integer NOT NULL, source_content_hash varchar(64) NOT NULL, source_anchor varchar(512) NOT NULL,
   valid_until date NOT NULL, status varchar(16) NOT NULL DEFAULT 'draft', created_by uuid NOT NULL, reviewer_id uuid,
   review_reason text, reviewed_at timestamptz, version integer NOT NULL DEFAULT 1, created_at timestamptz NOT NULL DEFAULT now(),
   CONSTRAINT ck_sales_claim_status CHECK (status in ('draft', 'approved', 'revoked')),
   CONSTRAINT ck_sales_claim_version CHECK (version > 0 AND source_version > 0))""",
  "CREATE INDEX IF NOT EXISTS ix_sales_claims_org_id ON sales_claims(org_id)",
  "CREATE INDEX IF NOT EXISTS ix_sales_claims_opportunity_id ON sales_claims(opportunity_id)",
  "CREATE INDEX IF NOT EXISTS ix_sales_claims_opportunity_status ON sales_claims(opportunity_id,status)",
 ],True),
 ("0036_sales_claims_rls",[],True),
 ("0037_sso_transactions", ["CREATE TABLE IF NOT EXISTS sso_transactions (state_hash varchar(64) PRIMARY KEY, binding_hash varchar(64) NOT NULL, protocol varchar(16) NOT NULL, nonce varchar(128) NOT NULL, verifier varchar(128) NOT NULL, expires_at double precision NOT NULL)", "CREATE INDEX IF NOT EXISTS ix_sso_transactions_expires_at ON sso_transactions(expires_at)"], True),
 ("0038_audit_rls_hardening",[],True),
 ("0040_audit_tenant_parent_guards",[],True),
 ("0039_audit_query_indexes",[
  "CREATE INDEX IF NOT EXISTS ix_documents_org_workspace_created ON documents(org_id, workspace_id, uploaded_at, id)",
  "CREATE INDEX IF NOT EXISTS ix_messages_conversation_created ON messages(conversation_id, created_at DESC, id DESC)",
  "CREATE INDEX IF NOT EXISTS ix_notes_org_workspace_updated ON notes(org_id, workspace_id, updated_at, id)",
  "CREATE INDEX IF NOT EXISTS ix_product_edges_workspace_status ON product_edges(workspace_id, status)",
 ],True),
 ("0041_identity_and_offline_rls",[],True),
 ("0042_audit_access_path_indexes",[
  "CREATE INDEX IF NOT EXISTS ix_documents_org_uploaded ON documents(org_id, uploaded_at DESC, id DESC)",
  "CREATE INDEX IF NOT EXISTS ix_conversations_org_workspace_updated ON conversations(org_id, workspace_id, updated_at DESC, id DESC)",
  "CREATE INDEX IF NOT EXISTS ix_ingestion_jobs_claim_order ON ingestion_jobs(status, run_after, created_at)",
  "CREATE INDEX IF NOT EXISTS ix_task_executions_claim_order ON task_executions(status, run_after, created_at)",
  "CREATE INDEX IF NOT EXISTS ix_product_edges_workspace_status_created ON product_edges(workspace_id, status, created_at DESC, id DESC)",
  "CREATE INDEX IF NOT EXISTS ix_audit_logs_org_created ON audit_logs(org_id, created_at DESC, id DESC)",
  "CREATE INDEX IF NOT EXISTS ix_products_name_trgm ON products USING gin(name gin_trgm_ops)",
  "CREATE INDEX IF NOT EXISTS ix_products_vendor_trgm ON products USING gin(vendor gin_trgm_ops)",
  "CREATE INDEX IF NOT EXISTS ix_products_category_trgm ON products USING gin(category gin_trgm_ops)",
 ],True),
 ("0043_retention_controls",[
  "CREATE TABLE IF NOT EXISTS retention_policies (org_id uuid PRIMARY KEY REFERENCES organizations(id) ON DELETE CASCADE, enabled boolean NOT NULL DEFAULT false, legal_hold boolean NOT NULL DEFAULT false, periods json NOT NULL DEFAULT '{}')",
  "CREATE TABLE IF NOT EXISTS retention_holds (id uuid PRIMARY KEY, org_id uuid NOT NULL REFERENCES organizations(id) ON DELETE CASCADE, kind varchar(32) NOT NULL, resource_id uuid NOT NULL, UNIQUE(org_id,kind,resource_id))",
  "CREATE INDEX IF NOT EXISTS ix_retention_holds_org_id ON retention_holds(org_id)",
  "CREATE TABLE IF NOT EXISTS retention_object_deletions (id uuid PRIMARY KEY, org_id uuid NOT NULL REFERENCES organizations(id) ON DELETE CASCADE, storage_key text NOT NULL, attempts integer NOT NULL DEFAULT 0)",
  "CREATE INDEX IF NOT EXISTS ix_retention_object_deletions_org_id ON retention_object_deletions(org_id)",
 ],True),
 ("0044_retention_rls",[],True),
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
  if name == "0040_audit_tenant_parent_guards":
   from app.db.tenant_constraints import apply_parent_guards
   apply_parent_guards(engine)
   with engine.begin() as conn: _record(conn,name)
   ran.append(name)
   continue
  if name in ("0038_audit_rls_hardening", "0041_identity_and_offline_rls"):
   _apply_rls(engine)
   _apply_derived_rls(engine)
   with engine.begin() as conn: _record(conn,name)
   ran.append(name)
   continue
  if name == "0044_retention_rls":
   _apply_rls(engine)
   from app.db.tenant_constraints import apply_parent_guards
   apply_parent_guards(engine)
   with engine.begin() as conn: _record(conn,name)
   ran.append(name)
   continue
  if name in ("0022_row_level_security", "0024_agent_actions_rls", "0026_sales_foundation_rls", "0028_opportunity_participants_rls", "0030_sales_commerce_rls", "0033_sales_quote_exports_rls", "0036_sales_claims_rls"):
   _apply_rls(engine)
   with engine.begin() as conn: _record(conn,name)
   ran.append(name)
   continue
  with engine.begin() as conn:
   for statement in statements:
    if not is_pg and "gen_random_uuid()" in statement.lower(): statement=statement.replace("gen_random_uuid()","lower(hex(randomblob(16)))")
    conn.execute(text(statement))
   _record(conn,name)
  ran.append(name)
 return ran
