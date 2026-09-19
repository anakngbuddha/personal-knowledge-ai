import uuid
from datetime import date, datetime

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Computed,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, TSVECTOR, UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

from app.core.config import settings
from app.security.labels import (
    DEFAULT_APPROVAL_STATE,
    DEFAULT_SENSITIVITY,
    ApprovalState,
    Ownership,
    Sensitivity,
    SourceType,
)

EMBEDDING_DIM = settings.gemini_embedding_dimensions
FTS_CONFIG = settings.fts_config


class Base(DeclarativeBase):
    pass


class DocumentStatus:
    UPLOADED = "uploaded"
    PROCESSING = "processing"
    READY = "ready"
    FAILED = "failed"
    QUARANTINED = "quarantined"


class JobStatus:
    QUEUED = "queued"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"  # will be retried
    DEAD = "dead"  # attempts exhausted, needs a human


class Organization(Base):
    """Tenant root. Phase 0 will add row-level security keyed on this column; the
    column exists now because retrofitting `org_id` into every query later is the
    one change Project_Plan.md calls genuinely painful."""

    __tablename__ = "organizations"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    slug: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class AccessGrant(Base):
    """Per-account read grant. Consumed by retrieval today, issued by an admin UI in Phase 6."""

    __tablename__ = "access_grants"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    org_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    account_ref: Mapped[str | None] = mapped_column(String(128))
    max_sensitivity: Mapped[str] = mapped_column(String(32), default=DEFAULT_SENSITIVITY)
    allow_vendor_restricted: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        UniqueConstraint("org_id", "user_id", "account_ref", name="uq_access_grant_scope"),
    )


class Workspace(Base):
    __tablename__ = "workspaces"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    org_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    documents: Mapped[list["Document"]] = relationship(back_populates="workspace")


class Document(Base):
    __tablename__ = "documents"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    org_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True
    )
    workspace_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False, index=True
    )

    # ------------------------------------------------------------------ file
    filename: Mapped[str] = mapped_column(String(512), nullable=False)
    original_filename: Mapped[str] = mapped_column(String(512), nullable=False)
    file_type: Mapped[str] = mapped_column(String(16), nullable=False)
    mime_type: Mapped[str | None] = mapped_column(String(128))
    declared_mime_type: Mapped[str | None] = mapped_column(String(128))
    storage_key: Mapped[str] = mapped_column(String(1024), nullable=False)
    file_size: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    content_hash: Mapped[str | None] = mapped_column(String(64), index=True)

    # ------------------------------------------------------- SE catalog metadata
    title: Mapped[str | None] = mapped_column(String(512))
    source_type: Mapped[str] = mapped_column(String(16), nullable=False, default=SourceType.UPLOAD)
    source_url: Mapped[str | None] = mapped_column(Text)
    source_of_truth_url: Mapped[str | None] = mapped_column(Text)
    vendor: Mapped[str | None] = mapped_column(String(255), index=True)
    ownership: Mapped[str] = mapped_column(String(16), nullable=False, default=Ownership.UNKNOWN)
    products_referenced: Mapped[list | None] = mapped_column(JSONB)
    account_ref: Mapped[str | None] = mapped_column(String(128), index=True)
    approval_state: Mapped[str] = mapped_column(
        String(16), nullable=False, default=DEFAULT_APPROVAL_STATE
    )
    sensitivity: Mapped[str] = mapped_column(
        String(24), nullable=False, default=DEFAULT_SENSITIVITY
    )
    valid_until: Mapped[date | None] = mapped_column(Date)
    metadata_complete: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    metadata_missing: Mapped[list | None] = mapped_column(JSONB)

    # --------------------------------------------------------------- versioning
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    supersedes_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("documents.id", ondelete="SET NULL")
    )
    is_current: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    # ------------------------------------------------------------- processing
    status: Mapped[str] = mapped_column(String(32), nullable=False, default=DocumentStatus.UPLOADED)
    page_count: Mapped[int | None] = mapped_column(Integer)
    chunk_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    ocr_applied: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    scan_result: Mapped[dict | None] = mapped_column(JSONB)
    injection_flag_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    doc_metadata: Mapped[dict | None] = mapped_column("metadata", JSONB)
    uploaded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    processed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    error_message: Mapped[str | None] = mapped_column(Text)

    workspace: Mapped[Workspace] = relationship(back_populates="documents")
    chunks: Mapped[list["DocumentChunk"]] = relationship(
        back_populates="document", cascade="all, delete-orphan", passive_deletes=True
    )

    __table_args__ = (
        CheckConstraint(
            "sensitivity in ("
            + ", ".join(f"'{s.value}'" for s in Sensitivity)
            + ")",
            name="ck_documents_sensitivity",
        ),
        CheckConstraint(
            "approval_state in ("
            + ", ".join(f"'{s.value}'" for s in ApprovalState)
            + ")",
            name="ck_documents_approval_state",
        ),
        # Deduplication is per workspace, and only across live versions: a
        # superseded copy keeps its hash for provenance without blocking re-upload.
        Index(
            "uq_documents_workspace_hash_current",
            "workspace_id",
            "content_hash",
            unique=True,
            postgresql_where=text("is_current"),
        ),
        Index("ix_documents_retrieval_filters", "workspace_id", "is_current", "status"),
    )


class DocumentChunk(Base):
    __tablename__ = "document_chunks"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    document_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("documents.id", ondelete="CASCADE"), nullable=False, index=True
    )
    org_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True
    )
    chunk_index: Mapped[int] = mapped_column(Integer, nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False)

    # ---------------------------------------------------------- citation anchors
    page_number: Mapped[int | None] = mapped_column(Integer)
    slide_number: Mapped[int | None] = mapped_column(Integer)
    sheet_name: Mapped[str | None] = mapped_column(String(255))
    cell_range: Mapped[str | None] = mapped_column(String(64))
    section_title: Mapped[str | None] = mapped_column(String(512))
    heading_path: Mapped[list | None] = mapped_column(JSONB)
    start_offset: Mapped[int | None] = mapped_column(Integer)
    end_offset: Mapped[int | None] = mapped_column(Integer)

    embedding: Mapped[list[float] | None] = mapped_column(Vector(EMBEDDING_DIM))
    # Generated column: kept in sync by PostgreSQL, never written by the app.
    search_vector: Mapped[str | None] = mapped_column(
        TSVECTOR, Computed(f"to_tsvector('{FTS_CONFIG}', text)", persisted=True)
    )
    injection_flags: Mapped[list | None] = mapped_column(JSONB)
    chunk_metadata: Mapped[dict | None] = mapped_column("metadata", JSONB)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    document: Mapped[Document] = relationship(back_populates="chunks")

    __table_args__ = (
        Index("ix_document_chunks_doc_idx", "document_id", "chunk_index", unique=True),
        Index("ix_document_chunks_search_vector", "search_vector", postgresql_using="gin"),
    )


class IngestionJob(Base):
    """Durable ingestion queue.

    Deviation from the plan, on purpose: FastAPI background tasks were used in the
    previous build, and they are lost on process restart. "Per-job status, retry
    with backoff, and a failed state" cannot be honoured by an in-memory task list,
    so the queue is a table. It is still a single worker, no Redis, no Celery.
    """

    __tablename__ = "ingestion_jobs"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    org_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True
    )
    document_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("documents.id", ondelete="CASCADE"), nullable=False, index=True
    )
    kind: Mapped[str] = mapped_column(String(32), nullable=False, default="ingest")
    status: Mapped[str] = mapped_column(String(16), nullable=False, default=JobStatus.QUEUED)
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    max_attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=4)
    run_after: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    locked_by: Mapped[str | None] = mapped_column(String(128))
    locked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    duration_seconds: Mapped[float | None] = mapped_column(Float)
    error_message: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    __table_args__ = (Index("ix_ingestion_jobs_claim", "status", "run_after"),)


class Conversation(Base):
    __tablename__ = "conversations"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    workspace_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False, index=True
    )
    title: Mapped[str | None] = mapped_column(String(512))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    messages: Mapped[list["Message"]] = relationship(
        back_populates="conversation", cascade="all, delete-orphan", passive_deletes=True
    )


class Message(Base):
    __tablename__ = "messages"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    conversation_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("conversations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    role: Mapped[str] = mapped_column(String(32), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    citations: Mapped[dict | None] = mapped_column(JSONB)
    # Phase 3: per-answer provenance
    sources: Mapped[list | None] = mapped_column(JSONB)  # structured SourceMetadata list
    usage: Mapped[dict | None] = mapped_column(JSONB)  # token counts
    prompt_version: Mapped[str | None] = mapped_column(String(32))
    refused: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    model_id: Mapped[str | None] = mapped_column(String(128))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    conversation: Mapped[Conversation] = relationship(back_populates="messages")


class EvaluationQuestion(Base):
    __tablename__ = "evaluation_questions"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    question: Mapped[str] = mapped_column(Text, nullable=False)
    expected_document_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("documents.id", ondelete="SET NULL")
    )
    expected_page_number: Mapped[int | None] = mapped_column(Integer)
    expected_chunk_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("document_chunks.id", ondelete="SET NULL")
    )
    # Substring match is the fallback label: chunk ids change whenever chunking
    # changes, and the labeled set must outlive a chunking tweak.
    expected_text_contains: Mapped[str | None] = mapped_column(Text)
    tags: Mapped[list | None] = mapped_column(JSONB)
    notes: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class SchemaMigration(Base):
    __tablename__ = "schema_migrations"

    name: Mapped[str] = mapped_column(String(128), primary_key=True)
    applied_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class TokenBudget(Base):
    """Per-org, per-month token budget for cost control.

    Project_Plan.md L195: per-org token budgets. Checked before generation
    and incremented after. A limit of 0 means unlimited.
    """

    __tablename__ = "token_budgets"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    org_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    month: Mapped[date] = mapped_column(Date, nullable=False)
    prompt_tokens_used: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    completion_tokens_used: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    prompt_token_limit: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    completion_token_limit: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    __table_args__ = (
        UniqueConstraint("org_id", "month", name="uq_token_budget_org_month"),
    )
