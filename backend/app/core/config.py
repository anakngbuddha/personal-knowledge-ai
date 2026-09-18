from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """All runtime configuration. Nothing model- or provider-specific is hard-coded."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore", case_sensitive=False)

    environment: str = "development"
    log_level: str = "INFO"

    # Database
    database_url: str = "postgresql+psycopg://postgres:postgres@localhost:5432/pka"

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

    # Retrieval / ingestion knobs
    top_k: int = 8
    rrf_k: int = 60
    chunk_size: int = 1200
    chunk_overlap: int = 150
    embedding_batch_size: int = 16
    max_upload_mb: int = 25

    cors_origins: str = "http://localhost:5173"

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def r2_endpoint(self) -> str:
        if self.r2_endpoint_url:
            return self.r2_endpoint_url
        return f"https://{self.r2_account_id}.r2.cloudflarestorage.com"


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
