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
    for name, statements in MIGRATIONS:
        if name in done:
            continue
        logger.info("applying migration %s", name)
        with engine.begin() as conn:
            for statement in statements:
                conn.execute(text(statement))
            conn.execute(
                text("INSERT INTO schema_migrations (name) VALUES (:name) "
                     "ON CONFLICT (name) DO NOTHING"),
                {"name": name},
            )
        ran.append(name)
    return ran
