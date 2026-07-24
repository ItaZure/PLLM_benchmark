"""Application configuration loaded from environment variables."""
from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime settings sourced from environment / .env file."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # --- Application ---
    APP_NAME: str = "PLLM Benchmark"
    API_PREFIX: str = "/api"
    DEBUG: bool = False

    # --- Database ---
    # Async SQLAlchemy URL, e.g. postgresql+asyncpg://user:pass@host:5432/dbname
    DATABASE_URL: str = (
        "postgresql+asyncpg://pllm:pllm@localhost:5432/pllm_benchmark"
    )

    # --- CORS ---
    # Comma-separated list of allowed origins for the local frontend.
    CORS_ORIGINS: str = "http://localhost,http://localhost:8080,http://127.0.0.1:8080"

    @property
    def cors_origins_list(self) -> list[str]:
        return [o.strip() for o in self.CORS_ORIGINS.split(",") if o.strip()]

    @property
    def sync_database_url(self) -> str:
        """Sync URL used by Alembic (swaps asyncpg driver for psycopg2)."""
        return self.DATABASE_URL.replace("+asyncpg", "+psycopg2")


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
