from functools import lru_cache
from pydantic import field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore", case_sensitive=False)
    environment: str = "development"
    log_level: str = "INFO"
    port: int = 8000
    auto_migrate: bool = False
    database_url: str = "postgresql+psycopg://postgres:postgres@localhost:5432/pka"

    @field_validator("database_url", mode="before")
    @classmethod
    def normalize_database_url(cls, v: str) -> str:
        if isinstance(v, str):
            if v.startswith("postgres://"): return "postgresql+psycopg://" + v[11:]
            if v.startswith("postgresql://") and not v.startswith("postgresql+"): return "postgresql+psycopg://" + v[13:]
        return v

    # Unscoped sessions must not see tenant rows. Trusted background and bootstrap
    # code explicitly opts into system_session().
    rls_default_deny: bool = True
    rls_required: bool = False

    storage_backend: str = "r2"
    local_storage_dir: str = "./.storage"
    r2_account_id: str = ""
    r2_access_key_id: str = ""
    r2_secret_access_key: str = ""
    r2_bucket_name: str = ""
    r2_endpoint_url: str = ""

    embedding_provider: str = "gemini"
    gemini_api_key: str = ""
    gemini_api_base: str = "https://generativelanguage.googleapis.com/v1beta"
    gemini_embedding_model: str = "gemini-embedding-001"
    gemini_embedding_dimensions: int = 768
    gemini_generation_model: str = "gemini-2.5-flash"
    llm_provider: str = "gemini"
    openrouter_api_key: str = ""
    openrouter_api_base: str = "https://openrouter.ai/api/v1"
    openrouter_llm_model: str = "qwen/qwen3.8-27b:free"
    openrouter_embedding_model: str = "nvidia/nemotron-3-embed-1b:free"
    openrouter_embedding_dimensions: int = 2048

    generation_rate_limit_rpm: int = 20
    generation_rate_limit_tpd: int = 100000
    generation_max_context_chunks: int = 12
    generation_max_history_turns: int = 10
    generation_stream_enabled: bool = True
    generation_max_output_tokens: int = 4096
    generation_rerank_enabled: bool = True
    generation_rerank_candidates: int = 12
    generation_search_candidate_k: int = 20
    # Audit finding 5: strict (sources-only) is the default answer mode.
    generation_strict_default: bool = True
    # A cited sentence whose content words overlap the cited passage less than this
    # is flagged as weakly supported (lexical check, not an entailment model).
    claim_support_min_overlap: float = 0.25
    web_fallback_min_score: float = 0.15
    web_fallback_max_results: int = 3
    web_fallback_max_chars: int = 2500
    tool_max_rounds: int = 4
    tool_max_calls_per_round: int = 4

    mcp_enabled: bool = False
    mcp_credentials_key: str = ""
    brave_api_key: str = ""
    tavily_api_key: str = ""
    mcp_playwright_enabled: bool = False
    mcp_ms365_enabled: bool = False
    ms365_mcp_token: str = ""
    mcp_call_timeout_seconds: float = 45.0
    mcp_max_result_bytes: int = 32768
    mcp_tool_max_rounds: int = 8
    # Audit finding 3: external MCP tokens are short-lived and re-validated per call.
    mcp_token_default_minutes: int = 480
    mcp_token_max_minutes: int = 1440
    mcp_max_sse_sessions: int = 500
    # Audit finding 12: child MCP servers get a minimal environment and a private
    # working directory. Optional OS sandbox wrapper, e.g. "bwrap --unshare-all ..."
    # or "firejail --quiet --private"; empty means no wrapper.
    mcp_child_env_allowlist: str = "PATH,LANG,LC_ALL,TZ,NODE_OPTIONS"
    mcp_child_workdir: str = "./.mcp-sandbox"
    mcp_child_sandbox_command: str = ""

    notes_max_body_chars: int = 200000
    # Scheduled crawls can ingest many pages and spend model tokens while idle.
    freshness_worker_enabled: bool = False
    freshness_poll_seconds: float = 30.0
    freshness_default_interval_seconds: int = 86400
    freshness_max_bytes: int = 2000000
    freshness_max_pages: int = 50
    freshness_max_depth: int = 2
    freshness_request_delay_seconds: float = 1.0
    # Monitored pages are sources an operator chose. Approved so citations can
    # see them. Set false to leave scraped pages in the draft review queue.
    freshness_auto_approve: bool = False
    restore_drill_sla_seconds: float = 300.0
    sso_enabled: bool = False
    sso_credentials_key: str = ""
    oidc_issuer: str = ""
    oidc_client_id: str = ""
    oidc_client_secret: str = ""
    oidc_audience: str = ""
    oidc_redirect_uri: str = "http://localhost:8000/auth/oidc/callback"
    saml_entity_id: str = ""
    saml_acs_url: str = "http://localhost:8000/auth/saml/acs"
    saml_idp_issuer: str = ""
    saml_idp_secret: str = ""
    saml_allow_unsigned: bool = False
    saml_idp_certificate: str = ""
    saml_idp_sso_url: str = ""
    credentials_previous_keys: dict[str, str] = {}
    credentials_key_id: str = "v1"

    top_k: int = 8
    rrf_k: int = 60
    candidate_k: int = 50
    chunk_size: int = 1200
    chunk_overlap: int = 150
    embedding_batch_size: int = 16
    max_upload_mb: int = 25
    fts_config: str = "english"

    # 2.3 structure-aware chunking. Retrieve the narrow child, prompt with the parent
    # section, and never cut a table in half.
    chunk_parent_child_enabled: bool = True
    chunk_keep_tables_whole: bool = True
    chunk_prepend_heading: bool = True
    chunk_table_max_multiple: int = 4

    # 2.2 understand step. Only a confident reading is allowed to fill curated fields.
    document_understanding_enabled: bool = True
    understanding_min_confidence: float = 0.7
    understanding_max_chars: int = 12000

    # 3.1 read the product map out of each source. Everything it finds is a
    # suggestion: nodes land as suggested, relationships wait for a person.
    graph_extraction_enabled: bool = True
    graph_extract_max_chars: int = 16000
    graph_auto_accept_confidence: float = 0.85

    # 3.3 the product list starts empty. The sample catalog is a demo, not a default:
    # it only loads when this is on, and everything it creates is stamped as demo
    # material so it can never be quoted back in an answer.
    demo_seed_catalog: bool = False
    catalog_import_max_rows: int = 2000
    catalog_import_max_bytes: int = 5242880

    # 3.5 answer with the map, not only with passages. When a question names a product
    # we know, walk a hop or two and bring the neighbours' best passages along.
    graph_expansion_enabled: bool = True
    graph_expansion_hops: int = 2
    graph_expansion_max_neighbours: int = 6
    graph_expansion_chunks_per_neighbour: int = 1
    # Audit finding 9: each neighbour costs a full hybrid search (and an embedding
    # call). Cap how many run per answer and stop when the time budget is spent.
    graph_expansion_max_neighbour_searches: int = 3
    graph_expansion_time_budget_ms: float = 1500.0

    # 4.1 the customer brief. Requirement text is read once into a structured brief and
    # kept as a note, so the rest of the conversation can use it. Off falls back to the
    # deterministic reader, which is also what the offline test suite exercises.
    advisor_brief_extraction_enabled: bool = True
    advisor_brief_max_chars: int = 12000

    auth_mode: str = "jwt"
    default_org_slug: str = "default"
    default_org_name: str = "Default Organization"
    jwt_secret_key: str = ""
    jwt_algorithm: str = "HS256"
    jwt_access_token_expire_minutes: int = 1440
    allow_legacy_token_endpoint: bool = False

    parse_timeout_seconds: float = 120.0
    max_archive_entries: int = 2000
    max_uncompressed_mb: int = 400
    max_compression_ratio: float = 120.0
    max_pdf_pages: int = 3000
    max_extracted_chars: int = 20000000
    malware_scanner: str = "heuristic"
    clamav_host: str = ""
    clamav_port: int = 3310
    clamav_timeout_seconds: float = 30.0
    ocr_provider: str = "none"
    ocr_language: str = "eng"
    ocr_dpi: int = 200
    ocr_max_pages: int = 50
    # Shared Gemini quota (OCR + embeddings + chat). Raise only after confirming the
    # account's real limit: a higher local number just moves the wait to Gemini 429s.
    gemini_rpm: int = 10
    # Audit finding 7: background calls may not take the last N slots of any rolling
    # minute, so an interactive call never waits behind a full ingestion backlog.
    gemini_interactive_reserve: int = 2
    auto_approve_uploads: bool = True
    url_fetch_enabled: bool = True
    url_fetch_timeout_seconds: float = 20.0
    url_fetch_max_redirects: int = 3
    url_fetch_allow_private_ips: bool = False

    worker_enabled: bool = True
    worker_poll_seconds: float = 2.0
    worker_concurrency: int = 1
    job_max_attempts: int = 4
    job_backoff_base_seconds: float = 15.0
    job_backoff_max_seconds: float = 900.0
    # Audit finding 13: running jobs renew their lease every heartbeat, so the stale
    # interval only has to outlast a missed heartbeat or two, not the longest job.
    job_stale_seconds: float = 600.0
    job_heartbeat_seconds: float = 60.0
    workflow_worker_enabled: bool = True
    workflow_worker_concurrency: int = 1
    workflow_task_stale_seconds: float = 600.0
    workflow_task_max_attempts: int = 4
    cors_origins: str = "http://localhost:5173"

    # Audit finding 8: log event-loop lag and DB-pool pressure so contention on the
    # single web process is measured before paying for a separate worker service.
    runtime_metrics_enabled: bool = True
    runtime_metrics_interval_seconds: float = 30.0

    @model_validator(mode="after")
    def production_security(self):
        if self.environment.lower() == "production":
            if self.auth_mode != "jwt": raise ValueError("AUTH_MODE must be jwt in production")
            if not self.jwt_secret_key or len(self.jwt_secret_key) < 32: raise ValueError("JWT_SECRET_KEY must be at least 32 characters in production")
            if not self.rls_required: raise ValueError("RLS_REQUIRED must be true in production")
            if self.freshness_auto_approve: raise ValueError("FRESHNESS_AUTO_APPROVE must be false in production")
            if self.auto_approve_uploads: raise ValueError("AUTO_APPROVE_UPLOADS must be false in production")
            if self.url_fetch_allow_private_ips: raise ValueError("private URL fetching is prohibited in production")
            if self.malware_scanner != "clamav": raise ValueError("production ingestion requires ClamAV")
            if self.saml_allow_unsigned: raise ValueError("unsigned SAML is prohibited")
            if "*" in self.cors_origin_list: raise ValueError("CORS must use explicit origins")
        for key in (self.mcp_credentials_key, self.sso_credentials_key, *self.credentials_previous_keys.values()):
            if key:
                from cryptography.fernet import Fernet
                try: Fernet(key.encode("ascii"))
                except (ValueError, UnicodeError) as exc: raise ValueError("credential keys must be valid Fernet keys") from exc
        return self

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def r2_endpoint(self) -> str:
        return self.r2_endpoint_url or f"https://{self.r2_account_id}.r2.cloudflarestorage.com"

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
