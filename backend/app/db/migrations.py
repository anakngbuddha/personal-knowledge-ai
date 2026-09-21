"""Idempotent, recorded schema migrations.

The project had none: `Base.metadata.create_all` creates missing *tables* and will
happily leave an existing table without its new columns, which means an already
deployed database silently diverges from the models. Phase 1 adds fifteen columns to
`documents`, so that gap had to close before anything else.

This is deliberately not Alembic. Alembic is the right answer once there is more than
one deployment and more than one person, and `docs/PHASE1-2.md` records it as the next
step. What is here is the smallest thing that is safe: named steps, `IF NOT EXISTS`
DDL, applied once and recorded in `schema_migrations`.
"""

from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.engine import Engine

from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)

# (name, list of statements). Never edit an applied step: add a new one.
MIGRATIONS: list[tuple[str, list[str]]] = [
    (
        "0001_extensions",
        [
            "CREATE EXTENSION IF NOT EXISTS vector",
            "CREATE EXTENSION IF NOT EXISTS pg_trgm",
        ],
    ),
    (
        "0002_documents_catalog_metadata",
        [
            "ALTER TABLE documents ADD COLUMN IF NOT EXISTS org_id uuid REFERENCES organizations(id) ON DELETE CASCADE",
            "ALTER TABLE documents ADD COLUMN IF NOT EXISTS content_hash varchar(64)",
            "ALTER TABLE documents ADD COLUMN IF NOT EXISTS title varchar(512)",
            "ALTER TABLE documents ADD COLUMN IF NOT EXISTS declared_mime_type varchar(128)",
            "ALTER TABLE documents ADD COLUMN IF NOT EXISTS source_type varchar(16) NOT NULL DEFAULT 'upload'",
            "ALTER TABLE documents ADD COLUMN IF NOT EXISTS source_url text",
            "ALTER TABLE documents ADD COLUMN IF NOT EXISTS source_of_truth_url text",
            "ALTER TABLE documents ADD COLUMN IF NOT EXISTS vendor varchar(255)",
            "ALTER TABLE documents ADD COLUMN IF NOT EXISTS ownership varchar(16) NOT NULL DEFAULT 'unknown'",
            "ALTER TABLE documents ADD COLUMN IF NOT EXISTS products_referenced jsonb",
            "ALTER TABLE documents ADD COLUMN IF NOT EXISTS account_ref varchar(128)",
            "ALTER TABLE documents ADD COLUMN IF NOT EXISTS approval_state varchar(16) NOT NULL DEFAULT 'draft'",
            "ALTER TABLE documents ADD COLUMN IF NOT EXISTS sensitivity varchar(24) NOT NULL DEFAULT 'internal'",
            "ALTER TABLE documents ADD COLUMN IF NOT EXISTS valid_until date",
            "ALTER TABLE documents ADD COLUMN IF NOT EXISTS metadata_complete boolean NOT NULL DEFAULT false",
            "ALTER TABLE documents ADD COLUMN IF NOT EXISTS metadata_missing jsonb",
            "ALTER TABLE documents ADD COLUMN IF NOT EXISTS version integer NOT NULL DEFAULT 1",
            "ALTER TABLE documents ADD COLUMN IF NOT EXISTS supersedes_id uuid REFERENCES documents(id) ON DELETE SET NULL",
            "ALTER TABLE documents ADD COLUMN IF NOT EXISTS is_current boolean NOT NULL DEFAULT true",
            "ALTER TABLE documents ADD COLUMN IF NOT EXISTS ocr_applied boolean NOT NULL DEFAULT false",
            "ALTER TABLE documents ADD COLUMN IF NOT EXISTS scan_result jsonb",
            "ALTER TABLE documents ADD COLUMN IF NOT EXISTS injection_flag_count integer NOT NULL DEFAULT 0",
        ],
    ),
    (
        "0003_chunk_citation_anchors",
        [
            "ALTER TABLE document_chunks ADD COLUMN IF NOT EXISTS org_id uuid REFERENCES organizations(id) ON DELETE CASCADE",
            "ALTER TABLE document_chunks ADD COLUMN IF NOT EXISTS slide_number integer",
            "ALTER TABLE document_chunks ADD COLUMN IF NOT EXISTS sheet_name varchar(255)",
            "ALTER TABLE document_chunks ADD COLUMN IF NOT EXISTS cell_range varchar(64)",
            "ALTER TABLE document_chunks ADD COLUMN IF NOT EXISTS heading_path jsonb",
            "ALTER TABLE document_chunks ADD COLUMN IF NOT EXISTS injection_flags jsonb",
        ],
    ),
    (
        "0004_workspaces_org",
        [
            "ALTER TABLE workspaces ADD COLUMN IF NOT EXISTS org_id uuid REFERENCES organizations(id) ON DELETE CASCADE",
        ],
    ),
    (
        "0005_eval_questions_text_label",
        [
            "ALTER TABLE evaluation_questions ADD COLUMN IF NOT EXISTS expected_text_contains text",
            "ALTER TABLE evaluation_questions ADD COLUMN IF NOT EXISTS tags jsonb",
        ],
    ),
    (
        "0006_indexes",
        [
            "CREATE INDEX IF NOT EXISTS ix_documents_org_id ON documents (org_id)",
            "CREATE INDEX IF NOT EXISTS ix_documents_content_hash ON documents (content_hash)",
            "CREATE INDEX IF NOT EXISTS ix_documents_vendor ON documents (vendor)",
            "CREATE INDEX IF NOT EXISTS ix_documents_account_ref ON documents (account_ref)",
            "CREATE INDEX IF NOT EXISTS ix_documents_retrieval_filters ON documents (workspace_id, is_current, status)",
            "CREATE INDEX IF NOT EXISTS ix_documents_products_referenced ON documents USING gin (products_referenced jsonb_path_ops)",
            "CREATE UNIQUE INDEX IF NOT EXISTS uq_documents_workspace_hash_current ON documents (workspace_id, content_hash) WHERE is_current",
            "CREATE INDEX IF NOT EXISTS ix_document_chunks_org_id ON document_chunks (org_id)",
            "CREATE INDEX IF NOT EXISTS ix_ingestion_jobs_claim ON ingestion_jobs (status, run_after)",
        ],
    ),
    (
        "0007_vector_index",
        [
            # HNSW over cosine distance, matching the normalised embeddings.
            "CREATE INDEX IF NOT EXISTS ix_document_chunks_embedding_hnsw "
            "ON document_chunks USING hnsw (embedding vector_cosine_ops)",
        ],
    ),
    (
        "0008_backfill_search_vector_config",
        [
            # The generated FTS column must use the configured dictionary. If an older
            # database was created with a different one, this reports rather than
            # silently disagreeing with the query side.
            "DO $$ BEGIN "
            "IF NOT EXISTS (SELECT 1 FROM pg_ts_config WHERE cfgname = "
            f"'{settings.fts_config}') THEN "
            f"RAISE EXCEPTION 'text search configuration {settings.fts_config} does not exist'; "
            "END IF; END $$",
        ],
    ),
    (
        "0009_phase3_generation",
        [
            # Token budget table for per-org cost control
            "CREATE TABLE IF NOT EXISTS token_budgets ("
            "id uuid PRIMARY KEY DEFAULT gen_random_uuid(), "
            "org_id uuid NOT NULL REFERENCES organizations(id) ON DELETE CASCADE, "
            "month date NOT NULL, "
            "prompt_tokens_used integer NOT NULL DEFAULT 0, "
            "completion_tokens_used integer NOT NULL DEFAULT 0, "
            "prompt_token_limit integer NOT NULL DEFAULT 0, "
            "completion_token_limit integer NOT NULL DEFAULT 0, "
            "created_at timestamptz NOT NULL DEFAULT now(), "
            "updated_at timestamptz NOT NULL DEFAULT now(), "
            "CONSTRAINT uq_token_budget_org_month UNIQUE (org_id, month))",
            "CREATE INDEX IF NOT EXISTS ix_token_budgets_org_id ON token_budgets (org_id)",
            # Message table: Phase 3 provenance columns
            "ALTER TABLE messages ADD COLUMN IF NOT EXISTS sources jsonb",
            "ALTER TABLE messages ADD COLUMN IF NOT EXISTS usage jsonb",
            "ALTER TABLE messages ADD COLUMN IF NOT EXISTS prompt_version varchar(32)",
            "ALTER TABLE messages ADD COLUMN IF NOT EXISTS refused boolean NOT NULL DEFAULT false",
            "ALTER TABLE messages ADD COLUMN IF NOT EXISTS model_id varchar(128)",
        ],
    ),
    (
        "0010_phase4_product_graph",
        [
            # products table
            "CREATE TABLE IF NOT EXISTS products ("
            "id uuid PRIMARY KEY DEFAULT gen_random_uuid(), "
            "org_id uuid NOT NULL REFERENCES organizations(id) ON DELETE CASCADE, "
            "workspace_id uuid NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE, "
            "name varchar(512) NOT NULL, "
            "slug varchar(128) NOT NULL, "
            "vendor varchar(255) NOT NULL, "
            "ownership varchar(16) NOT NULL DEFAULT 'own', "
            "category varchar(128) NOT NULL, "
            "tier varchar(64) NOT NULL DEFAULT 'Core', "
            "deployment_model varchar(32) NOT NULL DEFAULT 'cloud', "
            "licensing_model varchar(64) NOT NULL DEFAULT 'subscription', "
            "target_segment varchar(64) NOT NULL DEFAULT 'Enterprise', "
            "lifecycle_status varchar(32) NOT NULL DEFAULT 'GA', "
            "prerequisites text, "
            "support_path text, "
            "description text, "
            "collateral_document_ids jsonb, "
            "partner_tier varchar(128), "
            "margin_band varchar(64), "
            "support_owner varchar(64), "
            "contract_constraints text, "
            "source_of_truth_url text, "
            "created_at timestamptz NOT NULL DEFAULT now(), "
            "updated_at timestamptz NOT NULL DEFAULT now(), "
            "CONSTRAINT uq_products_workspace_slug UNIQUE (workspace_id, slug), "
            "CONSTRAINT ck_products_lifecycle_status CHECK (lifecycle_status IN ('GA', 'EOL', 'roadmap')), "
            "CONSTRAINT ck_products_deployment_model CHECK (deployment_model IN ('cloud', 'on-prem', 'hybrid')))",
            "CREATE INDEX IF NOT EXISTS ix_products_org_id ON products (org_id)",
            "CREATE INDEX IF NOT EXISTS ix_products_workspace_id ON products (workspace_id)",
            "CREATE INDEX IF NOT EXISTS ix_products_vendor ON products (vendor)",
            "CREATE INDEX IF NOT EXISTS ix_products_category ON products (category)",
            "CREATE INDEX IF NOT EXISTS ix_products_ownership ON products (ownership)",
            # capabilities table
            "CREATE TABLE IF NOT EXISTS capabilities ("
            "id uuid PRIMARY KEY DEFAULT gen_random_uuid(), "
            "org_id uuid NOT NULL REFERENCES organizations(id) ON DELETE CASCADE, "
            "name varchar(255) NOT NULL, "
            "slug varchar(128) NOT NULL, "
            "category varchar(128) NOT NULL, "
            "description text, "
            "created_at timestamptz NOT NULL DEFAULT now(), "
            "CONSTRAINT uq_capabilities_org_slug UNIQUE (org_id, slug))",
            "CREATE INDEX IF NOT EXISTS ix_capabilities_org_id ON capabilities (org_id)",
            "CREATE INDEX IF NOT EXISTS ix_capabilities_category ON capabilities (category)",
            # product_capabilities association table
            "CREATE TABLE IF NOT EXISTS product_capabilities ("
            "id uuid PRIMARY KEY DEFAULT gen_random_uuid(), "
            "product_id uuid NOT NULL REFERENCES products(id) ON DELETE CASCADE, "
            "capability_id uuid NOT NULL REFERENCES capabilities(id) ON DELETE CASCADE, "
            "proficiency varchar(32) NOT NULL DEFAULT 'native', "
            "notes text, "
            "created_at timestamptz NOT NULL DEFAULT now(), "
            "CONSTRAINT uq_product_capability UNIQUE (product_id, capability_id))",
            "CREATE INDEX IF NOT EXISTS ix_product_capabilities_product_id ON product_capabilities (product_id)",
            "CREATE INDEX IF NOT EXISTS ix_product_capabilities_capability_id ON product_capabilities (capability_id)",
            # product_edges table
            "CREATE TABLE IF NOT EXISTS product_edges ("
            "id uuid PRIMARY KEY DEFAULT gen_random_uuid(), "
            "org_id uuid NOT NULL REFERENCES organizations(id) ON DELETE CASCADE, "
            "workspace_id uuid NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE, "
            "source_product_id uuid NOT NULL REFERENCES products(id) ON DELETE CASCADE, "
            "target_product_id uuid NOT NULL REFERENCES products(id) ON DELETE CASCADE, "
            "relation_type varchar(32) NOT NULL, "
            "evidence text NOT NULL, "
            "confidence float NOT NULL DEFAULT 1.0, "
            "document_id uuid REFERENCES documents(id) ON DELETE SET NULL, "
            "is_ai_suggested boolean NOT NULL DEFAULT false, "
            "status varchar(32) NOT NULL DEFAULT 'approved', "
            "rejection_reason text, "
            "created_at timestamptz NOT NULL DEFAULT now(), "
            "updated_at timestamptz NOT NULL DEFAULT now(), "
            "CONSTRAINT uq_product_edge_source_target_type UNIQUE (source_product_id, target_product_id, relation_type), "
            "CONSTRAINT ck_product_edges_relation_type CHECK (relation_type IN ('integrates_with', 'requires', 'conflicts_with', 'replaces', 'bundles_with', 'alternative_to', 'migrates_to')), "
            "CONSTRAINT ck_product_edges_status CHECK (status IN ('approved', 'pending_review', 'rejected')), "
            "CONSTRAINT ck_product_edges_evidence_required CHECK (length(trim(evidence)) > 0))",
            "CREATE INDEX IF NOT EXISTS ix_product_edges_source ON product_edges (source_product_id)",
            "CREATE INDEX IF NOT EXISTS ix_product_edges_target ON product_edges (target_product_id)",
            "CREATE INDEX IF NOT EXISTS ix_product_edges_relation ON product_edges (relation_type)",
            "CREATE INDEX IF NOT EXISTS ix_product_edges_status ON product_edges (status)",
            # reference_architectures table
            "CREATE TABLE IF NOT EXISTS reference_architectures ("
            "id uuid PRIMARY KEY DEFAULT gen_random_uuid(), "
            "org_id uuid NOT NULL REFERENCES organizations(id) ON DELETE CASCADE, "
            "workspace_id uuid NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE, "
            "name varchar(255) NOT NULL, "
            "slug varchar(128) NOT NULL, "
            "description text, "
            "architecture_overview text, "
            "target_segment varchar(64), "
            "created_at timestamptz NOT NULL DEFAULT now(), "
            "updated_at timestamptz NOT NULL DEFAULT now(), "
            "CONSTRAINT uq_ref_arch_workspace_slug UNIQUE (workspace_id, slug))",
            "CREATE INDEX IF NOT EXISTS ix_ref_arch_org_id ON reference_architectures (org_id)",
            "CREATE INDEX IF NOT EXISTS ix_ref_arch_workspace_id ON reference_architectures (workspace_id)",
            # reference_architecture_products association table
            "CREATE TABLE IF NOT EXISTS reference_architecture_products ("
            "id uuid PRIMARY KEY DEFAULT gen_random_uuid(), "
            "architecture_id uuid NOT NULL REFERENCES reference_architectures(id) ON DELETE CASCADE, "
            "product_id uuid NOT NULL REFERENCES products(id) ON DELETE CASCADE, "
            "role varchar(128) NOT NULL DEFAULT 'Component', "
            "notes text, "
            "CONSTRAINT uq_ref_arch_product UNIQUE (architecture_id, product_id))",
            "CREATE INDEX IF NOT EXISTS ix_ref_arch_prod_arch ON reference_architecture_products (architecture_id)",
            "CREATE INDEX IF NOT EXISTS ix_ref_arch_prod_prod ON reference_architecture_products (product_id)",
        ],
    ),
    (
        "0011_phase0_security_baseline_rls",
        [
            # Add org_id to conversations if missing
            "ALTER TABLE conversations ADD COLUMN IF NOT EXISTS org_id uuid REFERENCES organizations(id) ON DELETE CASCADE",
            "CREATE INDEX IF NOT EXISTS ix_conversations_org_id ON conversations (org_id)",
            # Backfill conversations org_id from workspaces
            "UPDATE conversations SET org_id = workspaces.org_id FROM workspaces WHERE conversations.workspace_id = workspaces.id AND conversations.org_id IS NULL",
            # Create audit_logs table
            "CREATE TABLE IF NOT EXISTS audit_logs ("
            "id uuid PRIMARY KEY DEFAULT gen_random_uuid(), "
            "org_id uuid NOT NULL REFERENCES organizations(id) ON DELETE CASCADE, "
            "user_id uuid, "
            "action varchar(64) NOT NULL, "
            "resource_type varchar(64) NOT NULL, "
            "resource_id varchar(128), "
            "details jsonb, "
            "created_at timestamptz NOT NULL DEFAULT now())",
            "CREATE INDEX IF NOT EXISTS ix_audit_logs_org_id ON audit_logs (org_id)",
            "CREATE INDEX IF NOT EXISTS ix_audit_logs_user_id ON audit_logs (user_id)",
            "CREATE INDEX IF NOT EXISTS ix_audit_logs_action ON audit_logs (action)",
            "CREATE INDEX IF NOT EXISTS ix_audit_logs_created_at ON audit_logs (created_at)",
            # Row-Level Security policies for all tenant-scoped tables
            # documents
            "ALTER TABLE documents ENABLE ROW LEVEL SECURITY",
            "ALTER TABLE documents FORCE ROW LEVEL SECURITY",
            "DROP POLICY IF EXISTS tenant_isolation_policy ON documents",
            "CREATE POLICY tenant_isolation_policy ON documents AS PERMISSIVE FOR ALL USING (org_id = NULLIF(current_setting('app.current_org_id', true), '')::uuid) WITH CHECK (org_id = NULLIF(current_setting('app.current_org_id', true), '')::uuid)",
            # document_chunks
            "ALTER TABLE document_chunks ENABLE ROW LEVEL SECURITY",
            "ALTER TABLE document_chunks FORCE ROW LEVEL SECURITY",
            "DROP POLICY IF EXISTS tenant_isolation_policy ON document_chunks",
            "CREATE POLICY tenant_isolation_policy ON document_chunks AS PERMISSIVE FOR ALL USING (org_id = NULLIF(current_setting('app.current_org_id', true), '')::uuid) WITH CHECK (org_id = NULLIF(current_setting('app.current_org_id', true), '')::uuid)",
            # products
            "ALTER TABLE products ENABLE ROW LEVEL SECURITY",
            "ALTER TABLE products FORCE ROW LEVEL SECURITY",
            "DROP POLICY IF EXISTS tenant_isolation_policy ON products",
            "CREATE POLICY tenant_isolation_policy ON products AS PERMISSIVE FOR ALL USING (org_id = NULLIF(current_setting('app.current_org_id', true), '')::uuid) WITH CHECK (org_id = NULLIF(current_setting('app.current_org_id', true), '')::uuid)",
            # product_edges
            "ALTER TABLE product_edges ENABLE ROW LEVEL SECURITY",
            "ALTER TABLE product_edges FORCE ROW LEVEL SECURITY",
            "DROP POLICY IF EXISTS tenant_isolation_policy ON product_edges",
            "CREATE POLICY tenant_isolation_policy ON product_edges AS PERMISSIVE FOR ALL USING (org_id = NULLIF(current_setting('app.current_org_id', true), '')::uuid) WITH CHECK (org_id = NULLIF(current_setting('app.current_org_id', true), '')::uuid)",
            # reference_architectures
            "ALTER TABLE reference_architectures ENABLE ROW LEVEL SECURITY",
            "ALTER TABLE reference_architectures FORCE ROW LEVEL SECURITY",
            "DROP POLICY IF EXISTS tenant_isolation_policy ON reference_architectures",
            "CREATE POLICY tenant_isolation_policy ON reference_architectures AS PERMISSIVE FOR ALL USING (org_id = NULLIF(current_setting('app.current_org_id', true), '')::uuid) WITH CHECK (org_id = NULLIF(current_setting('app.current_org_id', true), '')::uuid)",
            # conversations
            "ALTER TABLE conversations ENABLE ROW LEVEL SECURITY",
            "ALTER TABLE conversations FORCE ROW LEVEL SECURITY",
            "DROP POLICY IF EXISTS tenant_isolation_policy ON conversations",
            "CREATE POLICY tenant_isolation_policy ON conversations AS PERMISSIVE FOR ALL USING (org_id = NULLIF(current_setting('app.current_org_id', true), '')::uuid) WITH CHECK (org_id = NULLIF(current_setting('app.current_org_id', true), '')::uuid)",
            # workspaces
            "ALTER TABLE workspaces ENABLE ROW LEVEL SECURITY",
            "ALTER TABLE workspaces FORCE ROW LEVEL SECURITY",
            "DROP POLICY IF EXISTS tenant_isolation_policy ON workspaces",
            "CREATE POLICY tenant_isolation_policy ON workspaces AS PERMISSIVE FOR ALL USING (org_id = NULLIF(current_setting('app.current_org_id', true), '')::uuid) WITH CHECK (org_id = NULLIF(current_setting('app.current_org_id', true), '')::uuid)",
            # access_grants
            "ALTER TABLE access_grants ENABLE ROW LEVEL SECURITY",
            "ALTER TABLE access_grants FORCE ROW LEVEL SECURITY",
            "DROP POLICY IF EXISTS tenant_isolation_policy ON access_grants",
            "CREATE POLICY tenant_isolation_policy ON access_grants AS PERMISSIVE FOR ALL USING (org_id = NULLIF(current_setting('app.current_org_id', true), '')::uuid) WITH CHECK (org_id = NULLIF(current_setting('app.current_org_id', true), '')::uuid)",
            # ingestion_jobs
            "ALTER TABLE ingestion_jobs ENABLE ROW LEVEL SECURITY",
            "ALTER TABLE ingestion_jobs FORCE ROW LEVEL SECURITY",
            "DROP POLICY IF EXISTS tenant_isolation_policy ON ingestion_jobs",
            "CREATE POLICY tenant_isolation_policy ON ingestion_jobs AS PERMISSIVE FOR ALL USING (org_id = NULLIF(current_setting('app.current_org_id', true), '')::uuid) WITH CHECK (org_id = NULLIF(current_setting('app.current_org_id', true), '')::uuid)",
            # token_budgets
            "ALTER TABLE token_budgets ENABLE ROW LEVEL SECURITY",
            "ALTER TABLE token_budgets FORCE ROW LEVEL SECURITY",
            "DROP POLICY IF EXISTS tenant_isolation_policy ON token_budgets",
            "CREATE POLICY tenant_isolation_policy ON token_budgets AS PERMISSIVE FOR ALL USING (org_id = NULLIF(current_setting('app.current_org_id', true), '')::uuid) WITH CHECK (org_id = NULLIF(current_setting('app.current_org_id', true), '')::uuid)",
            # audit_logs
            "ALTER TABLE audit_logs ENABLE ROW LEVEL SECURITY",
            "ALTER TABLE audit_logs FORCE ROW LEVEL SECURITY",
            "DROP POLICY IF EXISTS tenant_isolation_policy ON audit_logs",
            "CREATE POLICY tenant_isolation_policy ON audit_logs AS PERMISSIVE FOR ALL USING (org_id = NULLIF(current_setting('app.current_org_id', true), '')::uuid) WITH CHECK (org_id = NULLIF(current_setting('app.current_org_id', true), '')::uuid)",
        ],
    ),
    (
        "0012_task_executions",
        [
            "CREATE TABLE IF NOT EXISTS workflow_runs ("
            "id uuid PRIMARY KEY DEFAULT gen_random_uuid(), "
            "org_id uuid NOT NULL REFERENCES organizations(id) ON DELETE CASCADE, "
            "workspace_id uuid NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE, "
            "playbook_slug varchar(128) NOT NULL, "
            "status varchar(32) NOT NULL DEFAULT 'pending', "
            "created_by uuid, "
            "principal_snapshot jsonb, "
            "input_payload jsonb, "
            "error_message text, "
            "created_at timestamptz NOT NULL DEFAULT now(), "
            "updated_at timestamptz NOT NULL DEFAULT now())",
            "CREATE INDEX IF NOT EXISTS ix_workflow_runs_org_id ON workflow_runs (org_id)",
            "CREATE INDEX IF NOT EXISTS ix_workflow_runs_workspace_id ON workflow_runs (workspace_id)",
            "CREATE INDEX IF NOT EXISTS ix_workflow_runs_status ON workflow_runs (status)",
            "CREATE TABLE IF NOT EXISTS task_executions ("
            "id uuid PRIMARY KEY DEFAULT gen_random_uuid(), "
            "workflow_run_id uuid NOT NULL REFERENCES workflow_runs(id) ON DELETE CASCADE, "
            "org_id uuid NOT NULL REFERENCES organizations(id) ON DELETE CASCADE, "
            "task_slug varchar(128) NOT NULL, "
            "depends_on_slugs jsonb, "
            "status varchar(32) NOT NULL DEFAULT 'pending', "
            "input_payload jsonb, "
            "output_payload jsonb, "
            "leased_until timestamptz, "
            "run_after timestamptz, "
            "worker_id varchar(128), "
            "retry_count integer NOT NULL DEFAULT 0, "
            "max_attempts integer NOT NULL DEFAULT 4, "
            "error_message text, "
            "created_at timestamptz NOT NULL DEFAULT now(), "
            "updated_at timestamptz NOT NULL DEFAULT now())",
            "CREATE UNIQUE INDEX IF NOT EXISTS uq_task_exec_run_slug ON task_executions (workflow_run_id, task_slug)",
            "CREATE INDEX IF NOT EXISTS ix_task_executions_claim ON task_executions (status, created_at)",
            "CREATE INDEX IF NOT EXISTS ix_task_executions_org_id ON task_executions (org_id)",
            "ALTER TABLE workflow_runs ENABLE ROW LEVEL SECURITY",
            "ALTER TABLE workflow_runs FORCE ROW LEVEL SECURITY",
            "DROP POLICY IF EXISTS tenant_isolation_policy ON workflow_runs",
            "CREATE POLICY tenant_isolation_policy ON workflow_runs AS PERMISSIVE FOR ALL USING (org_id = NULLIF(current_setting('app.current_org_id', true), '')::uuid) WITH CHECK (org_id = NULLIF(current_setting('app.current_org_id', true), '')::uuid)",
            "ALTER TABLE task_executions ENABLE ROW LEVEL SECURITY",
            "ALTER TABLE task_executions FORCE ROW LEVEL SECURITY",
            "DROP POLICY IF EXISTS tenant_isolation_policy ON task_executions",
            "CREATE POLICY tenant_isolation_policy ON task_executions AS PERMISSIVE FOR ALL USING (org_id = NULLIF(current_setting('app.current_org_id', true), '')::uuid) WITH CHECK (org_id = NULLIF(current_setting('app.current_org_id', true), '')::uuid)",
        ],
    ),
    (
        "0013_mcp_integrations",
        [
            "CREATE TABLE IF NOT EXISTS mcp_integrations ("
            "id uuid PRIMARY KEY DEFAULT gen_random_uuid(), "
            "org_id uuid NOT NULL REFERENCES organizations(id) ON DELETE CASCADE, "
            "server_slug varchar(32) NOT NULL, "
            "enabled boolean NOT NULL DEFAULT false, "
            "config jsonb, "
            "secret_ciphertext bytea, "
            "status varchar(32) NOT NULL DEFAULT 'disconnected', "
            "last_error text, "
            "created_at timestamptz NOT NULL DEFAULT now(), "
            "updated_at timestamptz NOT NULL DEFAULT now())",
            "CREATE UNIQUE INDEX IF NOT EXISTS uq_mcp_integrations_org_slug ON mcp_integrations (org_id, server_slug)",
            "CREATE INDEX IF NOT EXISTS ix_mcp_integrations_org_id ON mcp_integrations (org_id)",
            "ALTER TABLE mcp_integrations ENABLE ROW LEVEL SECURITY",
            "ALTER TABLE mcp_integrations FORCE ROW LEVEL SECURITY",
            "DROP POLICY IF EXISTS tenant_isolation_policy ON mcp_integrations",
            "CREATE POLICY tenant_isolation_policy ON mcp_integrations AS PERMISSIVE FOR ALL USING (org_id = NULLIF(current_setting('app.current_org_id', true), '')::uuid) WITH CHECK (org_id = NULLIF(current_setting('app.current_org_id', true), '')::uuid)",
        ],
    ),
    (
        "0014_phase10_notes_freshness_sso",
        [
            "CREATE TABLE IF NOT EXISTS notes ("
            "id uuid PRIMARY KEY DEFAULT gen_random_uuid(), "
            "org_id uuid NOT NULL REFERENCES organizations(id) ON DELETE CASCADE, "
            "workspace_id uuid NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE, "
            "title varchar(512) NOT NULL, "
            "slug varchar(128) NOT NULL, "
            "body text NOT NULL DEFAULT '', "
            "created_by uuid, "
            "created_at timestamptz NOT NULL DEFAULT now(), "
            "updated_at timestamptz NOT NULL DEFAULT now(), "
            "CONSTRAINT uq_notes_workspace_slug UNIQUE (workspace_id, slug))",
            "CREATE INDEX IF NOT EXISTS ix_notes_org_id ON notes (org_id)",
            "CREATE INDEX IF NOT EXISTS ix_notes_workspace_id ON notes (workspace_id)",
            "CREATE TABLE IF NOT EXISTS note_links ("
            "id uuid PRIMARY KEY DEFAULT gen_random_uuid(), "
            "org_id uuid NOT NULL REFERENCES organizations(id) ON DELETE CASCADE, "
            "note_id uuid NOT NULL REFERENCES notes(id) ON DELETE CASCADE, "
            "target_kind varchar(16) NOT NULL, "
            "target_ref varchar(255) NOT NULL, "
            "display_text varchar(512), "
            "resolved boolean NOT NULL DEFAULT false, "
            "resolved_id uuid, "
            "CONSTRAINT ck_note_links_target_kind CHECK (target_kind IN ('product', 'account', 'note')))",
            "CREATE INDEX IF NOT EXISTS ix_note_links_note_id ON note_links (note_id)",
            "CREATE INDEX IF NOT EXISTS ix_note_links_target ON note_links (org_id, target_kind, target_ref)",
            "CREATE TABLE IF NOT EXISTS vendor_sources ("
            "id uuid PRIMARY KEY DEFAULT gen_random_uuid(), "
            "org_id uuid NOT NULL REFERENCES organizations(id) ON DELETE CASCADE, "
            "workspace_id uuid NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE, "
            "product_id uuid REFERENCES products(id) ON DELETE SET NULL, "
            "label varchar(255) NOT NULL, "
            "url text NOT NULL, "
            "enabled boolean NOT NULL DEFAULT true, "
            "check_interval_seconds integer NOT NULL DEFAULT 86400, "
            "status varchar(16) NOT NULL DEFAULT 'pending', "
            "last_hash varchar(64), "
            "last_etag varchar(255), "
            "last_modified_header varchar(255), "
            "last_checked_at timestamptz, "
            "next_check_at timestamptz NOT NULL DEFAULT now(), "
            "last_error text, "
            "locked_by varchar(128), "
            "locked_at timestamptz, "
            "created_at timestamptz NOT NULL DEFAULT now(), "
            "updated_at timestamptz NOT NULL DEFAULT now(), "
            "CONSTRAINT uq_vendor_sources_workspace_url UNIQUE (workspace_id, url))",
            "CREATE INDEX IF NOT EXISTS ix_vendor_sources_org_id ON vendor_sources (org_id)",
            "CREATE INDEX IF NOT EXISTS ix_vendor_sources_claim ON vendor_sources (enabled, status, next_check_at)",
            "CREATE TABLE IF NOT EXISTS freshness_alerts ("
            "id uuid PRIMARY KEY DEFAULT gen_random_uuid(), "
            "org_id uuid NOT NULL REFERENCES organizations(id) ON DELETE CASCADE, "
            "vendor_source_id uuid NOT NULL REFERENCES vendor_sources(id) ON DELETE CASCADE, "
            "kind varchar(32) NOT NULL DEFAULT 'content_changed', "
            "previous_hash varchar(64), "
            "new_hash varchar(64), "
            "acknowledged_at timestamptz, "
            "acknowledged_by uuid, "
            "details jsonb, "
            "created_at timestamptz NOT NULL DEFAULT now())",
            "CREATE INDEX IF NOT EXISTS ix_freshness_alerts_org_id ON freshness_alerts (org_id)",
            "CREATE INDEX IF NOT EXISTS ix_freshness_alerts_open ON freshness_alerts (org_id, acknowledged_at)",
            "CREATE TABLE IF NOT EXISTS restore_drills ("
            "id uuid PRIMARY KEY DEFAULT gen_random_uuid(), "
            "org_id uuid NOT NULL REFERENCES organizations(id) ON DELETE CASCADE, "
            "status varchar(16) NOT NULL DEFAULT 'running', "
            "sla_seconds float NOT NULL DEFAULT 300.0, "
            "duration_seconds float, "
            "within_sla boolean, "
            "row_counts_before jsonb, "
            "row_counts_after jsonb, "
            "triggered_by uuid, "
            "error_message text, "
            "started_at timestamptz NOT NULL DEFAULT now(), "
            "finished_at timestamptz)",
            "CREATE INDEX IF NOT EXISTS ix_restore_drills_org_id ON restore_drills (org_id)",
            "CREATE TABLE IF NOT EXISTS sso_providers ("
            "id uuid PRIMARY KEY DEFAULT gen_random_uuid(), "
            "org_id uuid NOT NULL REFERENCES organizations(id) ON DELETE CASCADE, "
            "protocol varchar(16) NOT NULL DEFAULT 'oidc', "
            "enabled boolean NOT NULL DEFAULT false, "
            "issuer varchar(512) NOT NULL, "
            "client_id varchar(255), "
            "audience varchar(255), "
            "secret_ciphertext bytea, "
            "metadata jsonb, "
            "created_at timestamptz NOT NULL DEFAULT now(), "
            "updated_at timestamptz NOT NULL DEFAULT now(), "
            "CONSTRAINT uq_sso_providers_org_protocol UNIQUE (org_id, protocol), "
            "CONSTRAINT ck_sso_providers_protocol CHECK (protocol IN ('oidc', 'saml')))",
            "CREATE INDEX IF NOT EXISTS ix_sso_providers_org_id ON sso_providers (org_id)",
            "ALTER TABLE notes ENABLE ROW LEVEL SECURITY",
            "ALTER TABLE notes FORCE ROW LEVEL SECURITY",
            "DROP POLICY IF EXISTS tenant_isolation_policy ON notes",
            "CREATE POLICY tenant_isolation_policy ON notes AS PERMISSIVE FOR ALL USING (org_id = NULLIF(current_setting('app.current_org_id', true), '')::uuid) WITH CHECK (org_id = NULLIF(current_setting('app.current_org_id', true), '')::uuid)",
            "ALTER TABLE note_links ENABLE ROW LEVEL SECURITY",
            "ALTER TABLE note_links FORCE ROW LEVEL SECURITY",
            "DROP POLICY IF EXISTS tenant_isolation_policy ON note_links",
            "CREATE POLICY tenant_isolation_policy ON note_links AS PERMISSIVE FOR ALL USING (org_id = NULLIF(current_setting('app.current_org_id', true), '')::uuid) WITH CHECK (org_id = NULLIF(current_setting('app.current_org_id', true), '')::uuid)",
            "ALTER TABLE vendor_sources ENABLE ROW LEVEL SECURITY",
            "ALTER TABLE vendor_sources FORCE ROW LEVEL SECURITY",
            "DROP POLICY IF EXISTS tenant_isolation_policy ON vendor_sources",
            "CREATE POLICY tenant_isolation_policy ON vendor_sources AS PERMISSIVE FOR ALL USING (org_id = NULLIF(current_setting('app.current_org_id', true), '')::uuid) WITH CHECK (org_id = NULLIF(current_setting('app.current_org_id', true), '')::uuid)",
            "ALTER TABLE freshness_alerts ENABLE ROW LEVEL SECURITY",
            "ALTER TABLE freshness_alerts FORCE ROW LEVEL SECURITY",
            "DROP POLICY IF EXISTS tenant_isolation_policy ON freshness_alerts",
            "CREATE POLICY tenant_isolation_policy ON freshness_alerts AS PERMISSIVE FOR ALL USING (org_id = NULLIF(current_setting('app.current_org_id', true), '')::uuid) WITH CHECK (org_id = NULLIF(current_setting('app.current_org_id', true), '')::uuid)",
            "ALTER TABLE restore_drills ENABLE ROW LEVEL SECURITY",
            "ALTER TABLE restore_drills FORCE ROW LEVEL SECURITY",
            "DROP POLICY IF EXISTS tenant_isolation_policy ON restore_drills",
            "CREATE POLICY tenant_isolation_policy ON restore_drills AS PERMISSIVE FOR ALL USING (org_id = NULLIF(current_setting('app.current_org_id', true), '')::uuid) WITH CHECK (org_id = NULLIF(current_setting('app.current_org_id', true), '')::uuid)",
            "ALTER TABLE sso_providers ENABLE ROW LEVEL SECURITY",
            "ALTER TABLE sso_providers FORCE ROW LEVEL SECURITY",
            "DROP POLICY IF EXISTS tenant_isolation_policy ON sso_providers",
            "CREATE POLICY tenant_isolation_policy ON sso_providers AS PERMISSIVE FOR ALL USING (org_id = NULLIF(current_setting('app.current_org_id', true), '')::uuid) WITH CHECK (org_id = NULLIF(current_setting('app.current_org_id', true), '')::uuid)",
        ],
    ),
]


def applied_migrations(engine: Engine) -> set[str]:
    with engine.begin() as conn:
        conn.execute(
            text(
                "CREATE TABLE IF NOT EXISTS schema_migrations ("
                "name varchar(128) PRIMARY KEY, "
                "applied_at timestamptz NOT NULL DEFAULT now())"
            )
        )
        rows = conn.execute(text("SELECT name FROM schema_migrations")).scalars().all()
    return set(rows)


def run_migrations(engine: Engine) -> list[str]:
    """Apply every unapplied step. Returns the names that ran."""
    done = applied_migrations(engine)
    ran: list[str] = []
    is_postgres = engine.dialect.name == "postgresql"
    for name, statements in MIGRATIONS:
        if name in done:
            continue
        logger.info("applying migration %s", name)
        with engine.begin() as conn:
            for statement in statements:
                if not is_postgres:
                    # Skip postgres-only RLS and specific DDL for in-memory SQLite test fixtures
                    upper = statement.upper()
                    if "ROW LEVEL SECURITY" in upper or "CREATE POLICY" in upper or "DROP POLICY" in upper:
                        continue
                    if "GEN_RANDOM_UUID()" in upper:
                        statement = statement.replace("gen_random_uuid()", "lower(hex(randomblob(16)))")
                    if "BYTEA" in upper:
                        statement = statement.replace("bytea", "BLOB").replace("BYTEA", "BLOB")
                conn.execute(text(statement))
            conn.execute(
                text("INSERT INTO schema_migrations (name) VALUES (:name) "
                     "ON CONFLICT (name) DO NOTHING"),
                {"name": name},
            )
        ran.append(name)
    return ran
