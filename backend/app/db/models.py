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
    LargeBinary,
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


def _sql_in_list(values) -> str:
    """Render a sorted SQL ``in (...)`` list so a CHECK constraint can never drift
    from the Python constants it is meant to mirror."""

    return ", ".join(f"'{value}'" for value in sorted(values))


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


class WorkflowRunStatus:
    PENDING = "pending"
    RUNNING = "running"
    WAITING_APPROVAL = "waiting_approval"
    SUCCEEDED = "succeeded"
    FAILED = "failed"


class TaskStatus:
    PENDING = "pending"
    RUNNING = "running"
    WAITING_APPROVAL = "waiting_approval"
    SUCCEEDED = "succeeded"
    FAILED = "failed"


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

    # 3.3 Sample material. The demo catalog and its collateral exist so the screens
    # have something to show on day one. An answer must never quote them back as if
    # they were the customer's own source, so retrieval drops them outright.
    is_demo: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, index=True)

    # --------------------------------------------------- what the source says
    # Written once by the 2.2 understand step, then editable by hand. These are a
    # reading of the document, not curated truth: `vendor`, `products_referenced`,
    # and `valid_until` above are only auto-filled from them when the model is
    # confident and the curated field is still blank.
    summary: Mapped[str | None] = mapped_column(Text)
    key_facts: Mapped[list | None] = mapped_column(JSONB)
    topic_tags: Mapped[list | None] = mapped_column(JSONB)
    detected_doc_type: Mapped[str | None] = mapped_column(String(64))
    detected_vendors: Mapped[list | None] = mapped_column(JSONB)
    detected_products: Mapped[list | None] = mapped_column(JSONB)
    detected_version_label: Mapped[str | None] = mapped_column(String(128))
    understanding_confidence: Mapped[float | None] = mapped_column(Float)
    understanding_source: Mapped[str | None] = mapped_column(String(16))  # llm | heuristic
    understood_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

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
    # Carries the 2.3 parent passage and table flag alongside the citation label, so
    # retrieval can match a narrow child and still prompt with the full section.
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
    document_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("documents.id", ondelete="CASCADE"), index=True
    )
    kind: Mapped[str] = mapped_column(String(32), nullable=False, default="ingest")
    payload: Mapped[dict | None] = mapped_column(JSONB)
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
    org_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True
    )
    workspace_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False, index=True
    )
    title: Mapped[str | None] = mapped_column(String(512))
    # 4.4 A thread belongs to one notebook. Null threads predate notebooks and stay
    # visible at the workspace level.
    notebook_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("notebooks.id", ondelete="SET NULL"), index=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    messages: Mapped[list["Message"]] = relationship(
        back_populates="conversation", cascade="all, delete-orphan", passive_deletes=True
    )


class AgentAction(Base):
    """A single audited workspace action awaiting explicit user confirmation."""

    __tablename__ = "agent_actions"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    org_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    workspace_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), index=True)
    conversation_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("conversations.id", ondelete="SET NULL"))
    kind: Mapped[str] = mapped_column(String(64), nullable=False)
    arguments: Mapped[dict] = mapped_column(JSONB, nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="pending")
    idempotency_key: Mapped[str] = mapped_column(String(128), nullable=False, unique=True)
    result: Mapped[dict | None] = mapped_column(JSONB)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


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


# ---------------------------------------------------------------------------
# Phase 4: Product Catalog & Typed Graph Models
# ---------------------------------------------------------------------------


class RelationType:
    """How two products relate.

    The first block is the original technical vocabulary. The second block (3.2) is
    the selling vocabulary: what a salesperson actually needs to say out loud when
    putting a bundle together.
    """

    INTEGRATES_WITH = "integrates_with"
    REQUIRES = "requires"
    CONFLICTS_WITH = "conflicts_with"
    REPLACES = "replaces"
    BUNDLES_WITH = "bundles_with"
    ALTERNATIVE_TO = "alternative_to"
    MIGRATES_TO = "migrates_to"

    # --- selling model (3.2) -------------------------------------------------
    RECOMMENDED_WITH = "recommended_with"
    CROSS_SELL = "cross_sell"
    UPSELL_TO = "upsell_to"
    CERTIFIED_FOR = "certified_for"
    REQUIRES_LICENSE = "requires_license"
    BUNDLE_COMPONENT = "bundle_component"
    SUITS_USE_CASE = "suits_use_case"

    ALL = {
        INTEGRATES_WITH,
        REQUIRES,
        CONFLICTS_WITH,
        REPLACES,
        BUNDLES_WITH,
        ALTERNATIVE_TO,
        MIGRATES_TO,
        RECOMMENDED_WITH,
        CROSS_SELL,
        UPSELL_TO,
        CERTIFIED_FOR,
        REQUIRES_LICENSE,
        BUNDLE_COMPONENT,
        SUITS_USE_CASE,
    }

    # Relations worth walking when we expand a question to nearby products (3.5).
    EXPANDABLE = {
        INTEGRATES_WITH,
        REQUIRES,
        CONFLICTS_WITH,
        BUNDLES_WITH,
        RECOMMENDED_WITH,
        CROSS_SELL,
        UPSELL_TO,
        BUNDLE_COMPONENT,
    }

    # Plain words for every relation, so no screen has to invent its own wording.
    WORDS = {
        INTEGRATES_WITH: "works with",
        REQUIRES: "needs",
        CONFLICTS_WITH: "clashes with",
        REPLACES: "replaces",
        BUNDLES_WITH: "is sold together with",
        ALTERNATIVE_TO: "is an alternative to",
        MIGRATES_TO: "moves customers to",
        RECOMMENDED_WITH: "is recommended with",
        CROSS_SELL: "pairs well with",
        UPSELL_TO: "is a step up to",
        CERTIFIED_FOR: "is certified for",
        REQUIRES_LICENSE: "needs a licence for",
        BUNDLE_COMPONENT: "is part of",
        SUITS_USE_CASE: "suits",
    }

    @classmethod
    def words(cls, relation_type: str) -> str:
        return cls.WORDS.get(relation_type, relation_type.replace("_", " "))


class EdgeStatus:
    APPROVED = "approved"
    PENDING_REVIEW = "pending_review"
    REJECTED = "rejected"

    ALL = {APPROVED, PENDING_REVIEW, REJECTED}


class CurationStatus:
    """Whether a node on the map was put there by a person or proposed by a read."""

    CONFIRMED = "confirmed"
    SUGGESTED = "suggested"

    ALL = {CONFIRMED, SUGGESTED}


class ContextKind:
    """The non-product things a product can be sold against (3.2)."""

    USE_CASE = "use_case"
    ROOM_TYPE = "room_type"
    PLATFORM = "platform"

    ALL = {USE_CASE, ROOM_TYPE, PLATFORM}

    WORDS = {
        USE_CASE: "use case",
        ROOM_TYPE: "room type",
        PLATFORM: "platform",
    }


class CapabilityCategory:
    """Canonical buckets for what a product can do.

    ``Capability.category`` stays a free string so nothing breaks, but these are the
    names the read step and the map UI use, which keeps the map from sprouting five
    spellings of "headset".
    """

    AUDIO = "audio"
    VIDEO = "video"
    HEADSETS = "headsets"
    CONFERENCING = "conferencing"
    CLOUD = "cloud"
    NETWORKING = "networking"
    MANAGEMENT = "management"
    SECURITY = "security"
    OTHER = "other"

    ALL = {AUDIO, VIDEO, HEADSETS, CONFERENCING, CLOUD, NETWORKING, MANAGEMENT, SECURITY, OTHER}

    # Words we have actually seen in vendor material, mapped to a bucket.
    ALIASES = {
        "audio": AUDIO,
        "sound": AUDIO,
        "speakerphone": AUDIO,
        "microphone": AUDIO,
        "mics": AUDIO,
        "ceiling microphone": AUDIO,
        "dsp": AUDIO,
        "video": VIDEO,
        "camera": VIDEO,
        "cameras": VIDEO,
        "display": VIDEO,
        "headset": HEADSETS,
        "headsets": HEADSETS,
        "earbuds": HEADSETS,
        "contact centre": HEADSETS,
        "contact center": HEADSETS,
        "conferencing": CONFERENCING,
        "meeting room": CONFERENCING,
        "meeting rooms": CONFERENCING,
        "room system": CONFERENCING,
        "uc": CONFERENCING,
        "unified communications": CONFERENCING,
        "cloud": CLOUD,
        "huawei cloud": CLOUD,
        "public cloud": CLOUD,
        "private cloud": CLOUD,
        "iaas": CLOUD,
        "paas": CLOUD,
        "saas": CLOUD,
        "network": NETWORKING,
        "networking": NETWORKING,
        "switching": NETWORKING,
        "wifi": NETWORKING,
        "wi-fi": NETWORKING,
        "management": MANAGEMENT,
        "device management": MANAGEMENT,
        "analytics": MANAGEMENT,
        "monitoring": MANAGEMENT,
        "security": SECURITY,
        "compliance": SECURITY,
    }

    @classmethod
    def normalize(cls, raw: str | None) -> str:
        if not raw:
            return cls.OTHER
        cleaned = raw.strip().lower()
        if cleaned in cls.ALL:
            return cleaned
        if cleaned in cls.ALIASES:
            return cls.ALIASES[cleaned]
        for alias, bucket in cls.ALIASES.items():
            if alias in cleaned:
                return bucket
        return cls.OTHER


class LifecycleStatus:
    GA = "GA"
    EOL = "EOL"
    ROADMAP = "roadmap"

    ALL = {GA, EOL, ROADMAP}


class DeploymentModel:
    CLOUD = "cloud"
    ON_PREM = "on-prem"
    HYBRID = "hybrid"

    ALL = {CLOUD, ON_PREM, HYBRID}


class Product(Base):
    __tablename__ = "products"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    org_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    workspace_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False, index=True
    )

    # Core entity attributes
    name: Mapped[str] = mapped_column(String(512), nullable=False)
    slug: Mapped[str] = mapped_column(String(128), nullable=False)
    vendor: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    ownership: Mapped[str] = mapped_column(String(16), nullable=False, default=Ownership.OWN)
    category: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    tier: Mapped[str] = mapped_column(String(64), nullable=False, default="Core")
    deployment_model: Mapped[str] = mapped_column(String(32), nullable=False, default="cloud")
    licensing_model: Mapped[str] = mapped_column(String(64), nullable=False, default="subscription")
    target_segment: Mapped[str] = mapped_column(String(64), nullable=False, default="Enterprise")
    lifecycle_status: Mapped[str] = mapped_column(String(32), nullable=False, default="GA")
    prerequisites: Mapped[str | None] = mapped_column(Text)
    support_path: Mapped[str | None] = mapped_column(Text)
    description: Mapped[str | None] = mapped_column(Text)
    collateral_document_ids: Mapped[list | None] = mapped_column(JSONB)

    # Where this product came from (3.1). A product read out of a source starts as
    # `suggested` and only joins the real product list once a person says so.
    curation_status: Mapped[str] = mapped_column(
        String(16), nullable=False, default=CurationStatus.CONFIRMED, index=True
    )
    is_ai_suggested: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    aliases: Mapped[list | None] = mapped_column(JSONB)
    source_document_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("documents.id", ondelete="SET NULL"), index=True
    )
    is_demo: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    # Resold-specific governance fields
    partner_tier: Mapped[str | None] = mapped_column(String(128))
    margin_band: Mapped[str | None] = mapped_column(String(64))
    support_owner: Mapped[str | None] = mapped_column(String(64))  # vendor | reseller | joint
    contract_constraints: Mapped[str | None] = mapped_column(Text)
    source_of_truth_url: Mapped[str | None] = mapped_column(Text)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    # Relationships
    capabilities: Mapped[list["ProductCapability"]] = relationship(
        back_populates="product", cascade="all, delete-orphan", passive_deletes=True
    )
    outgoing_edges: Mapped[list["ProductEdge"]] = relationship(
        "ProductEdge",
        foreign_keys="ProductEdge.source_product_id",
        back_populates="source_product",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    incoming_edges: Mapped[list["ProductEdge"]] = relationship(
        "ProductEdge",
        foreign_keys="ProductEdge.target_product_id",
        back_populates="target_product",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    context_links: Mapped[list["ProductContextLink"]] = relationship(
        back_populates="product", cascade="all, delete-orphan", passive_deletes=True
    )
    reference_architectures: Mapped[list["ReferenceArchitectureProduct"]] = relationship(
        back_populates="product", cascade="all, delete-orphan", passive_deletes=True
    )

    __table_args__ = (
        UniqueConstraint("workspace_id", "slug", name="uq_products_workspace_slug"),
        CheckConstraint(
            "lifecycle_status in ('GA', 'EOL', 'roadmap')",
            name="ck_products_lifecycle_status",
        ),
        CheckConstraint(
            "deployment_model in ('cloud', 'on-prem', 'hybrid')",
            name="ck_products_deployment_model",
        ),
        CheckConstraint(
            "curation_status in (" + _sql_in_list(CurationStatus.ALL) + ")",
            name="ck_products_curation_status",
        ),
    )


class Capability(Base):
    __tablename__ = "capabilities"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    org_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    slug: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    category: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    description: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    products: Mapped[list["ProductCapability"]] = relationship(
        back_populates="capability", cascade="all, delete-orphan", passive_deletes=True
    )

    __table_args__ = (
        UniqueConstraint("org_id", "slug", name="uq_capabilities_org_slug"),
    )


class ProductCapability(Base):
    __tablename__ = "product_capabilities"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    product_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("products.id", ondelete="CASCADE"), nullable=False, index=True
    )
    capability_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("capabilities.id", ondelete="CASCADE"), nullable=False, index=True
    )
    proficiency: Mapped[str] = mapped_column(String(32), nullable=False, default="native")
    notes: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    product: Mapped[Product] = relationship(back_populates="capabilities")
    capability: Mapped[Capability] = relationship(back_populates="products")

    __table_args__ = (
        UniqueConstraint("product_id", "capability_id", name="uq_product_capability"),
    )


class ProductEdge(Base):
    __tablename__ = "product_edges"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    org_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    workspace_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False, index=True
    )
    source_product_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("products.id", ondelete="CASCADE"), nullable=False, index=True
    )
    target_product_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("products.id", ondelete="CASCADE"), nullable=False, index=True
    )
    relation_type: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    evidence: Mapped[str] = mapped_column(Text, nullable=False)
    confidence: Mapped[float] = mapped_column(Float, nullable=False, default=1.0)
    document_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("documents.id", ondelete="SET NULL"), index=True
    )
    page_number: Mapped[int | None] = mapped_column(Integer)
    is_ai_suggested: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default=EdgeStatus.APPROVED, index=True)
    rejection_reason: Mapped[str | None] = mapped_column(Text)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    source_product: Mapped[Product] = relationship(
        "Product", foreign_keys=[source_product_id], back_populates="outgoing_edges"
    )
    target_product: Mapped[Product] = relationship(
        "Product", foreign_keys=[target_product_id], back_populates="incoming_edges"
    )
    document: Mapped[Document | None] = relationship("Document")

    __table_args__ = (
        UniqueConstraint(
            "source_product_id", "target_product_id", "relation_type", name="uq_product_edge_source_target_type"
        ),
        CheckConstraint(
            "relation_type in (" + _sql_in_list(RelationType.ALL) + ")",
            name="ck_product_edges_relation_type",
        ),
        CheckConstraint(
            "status in ('approved', 'pending_review', 'rejected')",
            name="ck_product_edges_status",
        ),
        CheckConstraint("length(trim(evidence)) > 0", name="ck_product_edges_evidence_required"),
    )


class SellingContext(Base):
    """A use case, room type, or platform a product can be sold against (3.2).

    One table instead of three: the three kinds carry exactly the same fields, and a
    single table keeps the map queries, the review queue, and the import path from
    being written three times.
    """

    __tablename__ = "selling_contexts"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    org_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    workspace_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False, index=True
    )
    kind: Mapped[str] = mapped_column(String(16), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    slug: Mapped[str] = mapped_column(String(128), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    aliases: Mapped[list | None] = mapped_column(JSONB)
    curation_status: Mapped[str] = mapped_column(
        String(16), nullable=False, default=CurationStatus.CONFIRMED, index=True
    )
    is_ai_suggested: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    source_document_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("documents.id", ondelete="SET NULL"), index=True
    )
    is_demo: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    product_links: Mapped[list["ProductContextLink"]] = relationship(
        back_populates="context", cascade="all, delete-orphan", passive_deletes=True
    )

    __table_args__ = (
        UniqueConstraint("workspace_id", "kind", "slug", name="uq_selling_contexts_workspace_kind_slug"),
        CheckConstraint(
            "kind in (" + _sql_in_list(ContextKind.ALL) + ")",
            name="ck_selling_contexts_kind",
        ),
        CheckConstraint(
            "curation_status in (" + _sql_in_list(CurationStatus.ALL) + ")",
            name="ck_selling_contexts_curation_status",
        ),
    )


class ProductContextLink(Base):
    """Product to use case / room type / platform, reviewed the same way as an edge."""

    __tablename__ = "product_context_links"

    # The relations that make sense against a context rather than another product.
    CONTEXT_RELATIONS = {
        RelationType.SUITS_USE_CASE,
        RelationType.CERTIFIED_FOR,
        RelationType.REQUIRES_LICENSE,
    }

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    org_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    workspace_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False, index=True
    )
    product_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("products.id", ondelete="CASCADE"), nullable=False, index=True
    )
    context_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("selling_contexts.id", ondelete="CASCADE"), nullable=False, index=True
    )
    relation_type: Mapped[str] = mapped_column(
        String(32), nullable=False, default=RelationType.SUITS_USE_CASE, index=True
    )
    evidence: Mapped[str] = mapped_column(Text, nullable=False)
    confidence: Mapped[float] = mapped_column(Float, nullable=False, default=1.0)
    document_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("documents.id", ondelete="SET NULL"), index=True
    )
    page_number: Mapped[int | None] = mapped_column(Integer)
    is_ai_suggested: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    status: Mapped[str] = mapped_column(
        String(32), nullable=False, default=EdgeStatus.APPROVED, index=True
    )
    rejection_reason: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    product: Mapped[Product] = relationship(back_populates="context_links")
    context: Mapped[SellingContext] = relationship(back_populates="product_links")
    document: Mapped[Document | None] = relationship("Document")

    __table_args__ = (
        UniqueConstraint(
            "product_id", "context_id", "relation_type", name="uq_product_context_link"
        ),
        CheckConstraint(
            "relation_type in ('suits_use_case', 'certified_for', 'requires_license')",
            name="ck_product_context_links_relation_type",
        ),
        CheckConstraint(
            "status in ('approved', 'pending_review', 'rejected')",
            name="ck_product_context_links_status",
        ),
        CheckConstraint(
            "length(trim(evidence)) > 0", name="ck_product_context_links_evidence_required"
        ),
    )


class ReferenceArchitecture(Base):
    __tablename__ = "reference_architectures"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    org_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    workspace_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    slug: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    description: Mapped[str | None] = mapped_column(Text)
    architecture_overview: Mapped[str | None] = mapped_column(Text)
    target_segment: Mapped[str | None] = mapped_column(String(64))

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    products: Mapped[list["ReferenceArchitectureProduct"]] = relationship(
        back_populates="architecture", cascade="all, delete-orphan", passive_deletes=True
    )

    __table_args__ = (
        UniqueConstraint("workspace_id", "slug", name="uq_ref_arch_workspace_slug"),
    )


class ReferenceArchitectureProduct(Base):
    __tablename__ = "reference_architecture_products"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    architecture_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("reference_architectures.id", ondelete="CASCADE"), nullable=False, index=True
    )
    product_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("products.id", ondelete="CASCADE"), nullable=False, index=True
    )
    role: Mapped[str] = mapped_column(String(128), nullable=False, default="Component")
    notes: Mapped[str | None] = mapped_column(Text)

    architecture: Mapped[ReferenceArchitecture] = relationship(back_populates="products")
    product: Mapped[Product] = relationship(back_populates="reference_architectures")

    __table_args__ = (
        UniqueConstraint("architecture_id", "product_id", name="uq_ref_arch_product"),
    )


class AuditLog(Base):
    """Append-only audit trail for sensitive tenant operations.

    Phase 0: Track user, tenant, action, resource, and timestamp.
    """

    __tablename__ = "audit_logs"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    org_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    user_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), index=True)
    action: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    resource_type: Mapped[str] = mapped_column(String(64), nullable=False)
    resource_id: Mapped[str | None] = mapped_column(String(128))
    details: Mapped[dict | None] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True
    )


class WorkflowRun(Base):
    """One execution of a playbook. Tasks are materialized up front."""

    __tablename__ = "workflow_runs"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    org_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    workspace_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False, index=True
    )
    playbook_slug: Mapped[str] = mapped_column(String(128), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default=WorkflowRunStatus.PENDING)
    created_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    principal_snapshot: Mapped[dict | None] = mapped_column(JSONB)
    input_payload: Mapped[dict | None] = mapped_column(JSONB)
    error_message: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    tasks: Mapped[list["TaskExecution"]] = relationship(
        back_populates="run", cascade="all, delete-orphan"
    )


class TaskExecution(Base):
    """One node in a materialized workflow DAG."""

    __tablename__ = "task_executions"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    workflow_run_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("workflow_runs.id", ondelete="CASCADE"), nullable=False, index=True
    )
    org_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    task_slug: Mapped[str] = mapped_column(String(128), nullable=False)
    depends_on_slugs: Mapped[list | None] = mapped_column(JSONB)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default=TaskStatus.PENDING)
    input_payload: Mapped[dict | None] = mapped_column(JSONB)
    output_payload: Mapped[dict | None] = mapped_column(JSONB)
    leased_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    run_after: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    worker_id: Mapped[str | None] = mapped_column(String(128))
    retry_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    max_attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=4)
    error_message: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    run: Mapped[WorkflowRun] = relationship(back_populates="tasks")

    __table_args__ = (
        UniqueConstraint("workflow_run_id", "task_slug", name="uq_task_exec_run_slug"),
        Index("ix_task_executions_claim", "status", "created_at"),
    )


class McpIntegration(Base):
    """Per-tenant MCP server enablement and encrypted credentials (Phase 9)."""

    __tablename__ = "mcp_integrations"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    org_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    server_slug: Mapped[str] = mapped_column(String(32), nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    config: Mapped[dict | None] = mapped_column(JSONB)
    secret_ciphertext: Mapped[bytes | None] = mapped_column(LargeBinary)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="disconnected")
    last_error: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    __table_args__ = (
        UniqueConstraint("org_id", "server_slug", name="uq_mcp_integrations_org_slug"),
    )


# ---------------------------------------------------------------------------
# Phase 10: Notes, Freshness & Enterprise Hardening
# ---------------------------------------------------------------------------


class Notebook(Base):
    """A named deal or customer inside a workspace.

    Sources stay owned by the workspace. A notebook only remembers which of them
    are switched on, plus the notes and chats that belong to this deal.
    """

    __tablename__ = "notebooks"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    org_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    workspace_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    sources: Mapped[list["NotebookSource"]] = relationship(
        back_populates="notebook", cascade="all, delete-orphan", passive_deletes=True
    )

    __table_args__ = (UniqueConstraint("workspace_id", "name", name="uq_notebooks_workspace_name"),)


class NotebookSource(Base):
    """Whether a workspace source is included when asking inside a notebook."""

    __tablename__ = "notebook_sources"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    org_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    notebook_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("notebooks.id", ondelete="CASCADE"), nullable=False, index=True
    )
    document_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("documents.id", ondelete="CASCADE"), nullable=False, index=True
    )
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    notebook: Mapped[Notebook] = relationship(back_populates="sources")

    __table_args__ = (
        UniqueConstraint("notebook_id", "document_id", name="uq_notebook_sources_pair"),
    )


class NoteLinkKind:
    PRODUCT = "product"
    ACCOUNT = "account"
    NOTE = "note"

    ALL = {PRODUCT, ACCOUNT, NOTE}


class FreshnessStatus:
    PENDING = "pending"
    FRESH = "fresh"
    STALE = "stale"
    ERROR = "error"

    ALL = {PENDING, FRESH, STALE, ERROR}


class RestoreDrillStatus:
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"

    ALL = {RUNNING, SUCCEEDED, FAILED}


class SsoProtocol:
    OIDC = "oidc"
    SAML = "saml"

    ALL = {OIDC, SAML}


class Note(Base):
    """SE tribal knowledge. Markdown body with [[wikilinks]] to products, accounts, notes."""

    __tablename__ = "notes"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    org_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    workspace_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False, index=True
    )
    notebook_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("notebooks.id", ondelete="SET NULL"), index=True
    )
    title: Mapped[str] = mapped_column(String(512), nullable=False)
    slug: Mapped[str] = mapped_column(String(128), nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False, default="")
    created_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    links: Mapped[list["NoteLink"]] = relationship(
        back_populates="note", cascade="all, delete-orphan", passive_deletes=True
    )

    __table_args__ = (UniqueConstraint("workspace_id", "slug", name="uq_notes_workspace_slug"),)


class NoteLink(Base):
    """A [[wikilink]] extracted from a note body on save."""

    __tablename__ = "note_links"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    org_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    note_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("notes.id", ondelete="CASCADE"), nullable=False, index=True
    )
    target_kind: Mapped[str] = mapped_column(String(16), nullable=False)
    target_ref: Mapped[str] = mapped_column(String(255), nullable=False)
    display_text: Mapped[str | None] = mapped_column(String(512))
    resolved: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    resolved_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))

    note: Mapped[Note] = relationship(back_populates="links")

    __table_args__ = (
        Index("ix_note_links_target", "org_id", "target_kind", "target_ref"),
        CheckConstraint(
            "target_kind in ('product', 'account', 'note')",
            name="ck_note_links_target_kind",
        ),
    )


class VendorSource(Base):
    """Upstream vendor URL monitored for datasheet / collateral changes."""

    __tablename__ = "vendor_sources"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    org_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    workspace_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False, index=True
    )
    product_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("products.id", ondelete="SET NULL"), index=True
    )
    label: Mapped[str] = mapped_column(String(255), nullable=False)
    url: Mapped[str] = mapped_column(Text, nullable=False)
    path_prefix: Mapped[str | None] = mapped_column(Text)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    check_interval_seconds: Mapped[int] = mapped_column(Integer, nullable=False, default=86400)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default=FreshnessStatus.PENDING)
    last_hash: Mapped[str | None] = mapped_column(String(64))
    last_etag: Mapped[str | None] = mapped_column(String(255))
    last_modified_header: Mapped[str | None] = mapped_column(String(255))
    last_checked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    next_check_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    last_error: Mapped[str | None] = mapped_column(Text)
    locked_by: Mapped[str | None] = mapped_column(String(128))
    locked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    alerts: Mapped[list["FreshnessAlert"]] = relationship(
        back_populates="source", cascade="all, delete-orphan", passive_deletes=True
    )
    pages: Mapped[list["VendorSourcePage"]] = relationship(
        back_populates="source", cascade="all, delete-orphan", passive_deletes=True
    )

    __table_args__ = (
        UniqueConstraint("workspace_id", "url", name="uq_vendor_sources_workspace_url"),
        Index("ix_vendor_sources_claim", "enabled", "status", "next_check_at"),
    )


class FreshnessAlert(Base):
    """Staleness alert raised when an upstream vendor document changes."""

    __tablename__ = "freshness_alerts"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    org_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    vendor_source_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("vendor_sources.id", ondelete="CASCADE"), nullable=False, index=True
    )
    kind: Mapped[str] = mapped_column(String(32), nullable=False, default="content_changed")
    previous_hash: Mapped[str | None] = mapped_column(String(64))
    new_hash: Mapped[str | None] = mapped_column(String(64))
    acknowledged_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    acknowledged_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    details: Mapped[dict | None] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    source: Mapped[VendorSource] = relationship(back_populates="alerts")

    __table_args__ = (Index("ix_freshness_alerts_open", "org_id", "acknowledged_at"),)


class VendorSourcePage(Base):
    """One crawled URL belonging to a vendor source, and the document it produced."""

    __tablename__ = "vendor_source_pages"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    org_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    vendor_source_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("vendor_sources.id", ondelete="CASCADE"), nullable=False, index=True
    )
    url: Mapped[str] = mapped_column(Text, nullable=False)
    document_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("documents.id", ondelete="SET NULL"), index=True
    )
    last_hash: Mapped[str | None] = mapped_column(String(64))
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    missing_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    source: Mapped[VendorSource] = relationship(back_populates="pages")

    __table_args__ = (
        UniqueConstraint("vendor_source_id", "url", name="uq_vendor_source_pages_url"),
    )


class RestoreDrill(Base):
    """Record of an automated disaster-recovery restore drill."""

    __tablename__ = "restore_drills"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    org_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    status: Mapped[str] = mapped_column(String(16), nullable=False, default=RestoreDrillStatus.RUNNING)
    sla_seconds: Mapped[float] = mapped_column(Float, nullable=False, default=300.0)
    duration_seconds: Mapped[float | None] = mapped_column(Float)
    within_sla: Mapped[bool | None] = mapped_column(Boolean)
    row_counts_before: Mapped[dict | None] = mapped_column(JSONB)
    row_counts_after: Mapped[dict | None] = mapped_column(JSONB)
    triggered_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    error_message: Mapped[str | None] = mapped_column(Text)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class SsoProvider(Base):
    """Per-tenant OIDC or SAML identity provider configuration."""

    __tablename__ = "sso_providers"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    org_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    protocol: Mapped[str] = mapped_column(String(16), nullable=False, default=SsoProtocol.OIDC)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    issuer: Mapped[str] = mapped_column(String(512), nullable=False)
    client_id: Mapped[str | None] = mapped_column(String(255))
    audience: Mapped[str | None] = mapped_column(String(255))
    secret_ciphertext: Mapped[bytes | None] = mapped_column(LargeBinary)
    idp_metadata: Mapped[dict | None] = mapped_column("metadata", JSONB)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    __table_args__ = (
        UniqueConstraint("org_id", "protocol", name="uq_sso_providers_org_protocol"),
        CheckConstraint("protocol in ('oidc', 'saml')", name="ck_sso_providers_protocol"),
    )
