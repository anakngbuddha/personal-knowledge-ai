from functools import lru_cache

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """All runtime configuration. Nothing model- or provider-specific is hard-coded."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore", case_sensitive=False)

    environment: str = "development"
    log_level: str = "INFO"

    # Database
    database_url: str = "postgresql+psycopg://postgres:postgres@localhost:5432/pka"

    @field_validator("database_url", mode="before")
    @classmethod
    def normalize_database_url(cls, v: str) -> str:
        if isinstance(v, str):
            if v.startswith("postgres://"):
                return "postgresql+psycopg://" + v[len("postgres://"):]
            if v.startswith("postgresql://") and not v.startswith("postgresql+"):
                return "postgresql+psycopg://" + v[len("postgresql://"):]
        return v

    # Object storage (Cloudflare R2)
    storage_backend: str = "r2"  # r2 | local
    local_storage_dir: str = "./.storage"
    r2_account_id: str = ""
    r2_access_key_id: str = ""
    r2_secret_access_key: str = ""
    r2_bucket_name: str = ""
    r2_endpoint_url: str = ""

    # Providers
    embedding_provider: str = "gemini"  # gemini | fake
    gemini_api_key: str = ""
    gemini_api_base: str = "https://generativelanguage.googleapis.com/v1beta"
    gemini_embedding_model: str = "gemini-embedding-001"
    gemini_embedding_dimensions: int = 768
    gemini_generation_model: str = "gemini-2.5-flash"

    # ----------------------------------------------------------- LLM generation
    llm_provider: str = "gemini"  # gemini | fake
    generation_rate_limit_rpm: int = 20  # per-user requests per minute
    generation_rate_limit_tpd: int = 100_000  # per-org tokens per day (0 = unlimited)
    generation_max_context_chunks: int = 12
    generation_max_history_turns: int = 10
    generation_stream_enabled: bool = True
    generation_max_output_tokens: int = 4096
    tool_max_rounds: int = 1
    tool_max_calls_per_round: int = 4

    # Retrieval / ingestion knobs
    top_k: int = 8
    rrf_k: int = 60
    candidate_k: int = 50  # per-branch candidates handed to fusion
    chunk_size: int = 1200
    chunk_overlap: int = 150
    embedding_batch_size: int = 16
    max_upload_mb: int = 25
    fts_config: str = "english"  # must match the generated column in the DB

    # ---------------------------------------------------------------- tenancy & auth
    # Phase 0 security baseline:
    # `jwt`: cryptographic token authentication via Authorization: Bearer <token>.
    # `owner_dev`: local development bypass resolving to default org owner.
    auth_mode: str = "owner_dev"  # jwt | owner_dev
    default_org_slug: str = "default"
    default_org_name: str = "Default Organization"
    jwt_secret_key: str = "dev-insecure-secret-key-change-in-production-2026"
    jwt_algorithm: str = "HS256"
    jwt_access_token_expire_minutes: int = 1440

    # ------------------------------------------------------------- ingestion
    # Parse-time safety limits. These are the controls that actually stop zip
    # bombs and pathological files, so they are configuration, not constants.
    parse_timeout_seconds: float = 120.0
    max_archive_entries: int = 2000
    max_uncompressed_mb: int = 400
    max_compression_ratio: float = 120.0
    max_pdf_pages: int = 3000
    max_extracted_chars: int = 20_000_000

    malware_scanner: str = "heuristic"  # none | heuristic | clamav
    clamav_host: str = ""
    clamav_port: int = 3310
    clamav_timeout_seconds: float = 30.0

    ocr_provider: str = "none"  # none | tesseract
    ocr_language: str = "eng"
    ocr_dpi: int = 200
    ocr_max_pages: int = 50

    # URL ingestion (SSRF-safe fetcher)
    url_fetch_enabled: bool = True
    url_fetch_timeout_seconds: float = 20.0
    url_fetch_max_redirects: int = 3
    url_fetch_allow_private_ips: bool = False  # tests only. Never enable in production.

    # Background worker
    worker_enabled: bool = True  # run the poller inside the API process
    worker_poll_seconds: float = 2.0
    worker_concurrency: int = 1
    job_max_attempts: int = 4
    job_backoff_base_seconds: float = 15.0
    job_backoff_max_seconds: float = 900.0
    job_stale_seconds: float = 1800.0
    workflow_worker_enabled: bool = True
    workflow_worker_concurrency: int = 1
    workflow_task_stale_seconds: float = 1800.0
    workflow_task_max_attempts: int = 4

    cors_origins: str = "http://localhost:5173"

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def r2_endpoint(self) -> str:
        if self.r2_endpoint_url:
            return self.r2_endpoint_url
        return f"https://{self.r2_account_id}.r2.cloudflarestorage.com"

    @property
    def max_upload_bytes(self) -> int:
        return self.max_upload_mb * 1024 * 1024

    @property
    def max_uncompressed_bytes(self) -> int:
        return self.max_uncompressed_mb * 1024 * 1024


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
