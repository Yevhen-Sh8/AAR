from functools import lru_cache

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_prefix="AAR_", extra="ignore")

    app_name: str = "AAR API"
    environment: str = "development"
    database_url: str = Field(
        default="postgresql+asyncpg://aar:aar@localhost:5432/aar"
    )
    redis_url: str = "redis://localhost:6379/0"
    jwt_secret: str = "change-me-in-production"
    jwt_algorithm: str = "HS256"
    jwt_expires_minutes: int = 60 * 8

    # CORS — comma-separated allow-list of exact origins, plus an optional regex
    # (e.g. to permit a preview-host wildcard). Leave empty unless needed.
    cors_origins: str = "http://localhost:5173,http://localhost:8080"
    cors_origin_regex: str = ""

    anthropic_api_key: str = ""
    llm_default_model: str = "claude-sonnet-4-6"
    llm_fast_model: str = "claude-haiku-4-5"
    llm_enabled: bool = False

    # Bootstrap admin — seeded on first start if absent. Override in prod.
    admin_email: str = "admin@aar.local"
    admin_password: str = "aar-admin-2026"

    # Login rate limiting (Wave 5 hardening) — in-process sliding window,
    # see core/rate_limit.py. No Redis dependency for this pilot deploy.
    login_rate_limit_attempts: int = 20
    login_rate_limit_window_seconds: float = 300.0

    # When true, the container entrypoint seeds synthetic demo data on first
    # boot (idempotent — skips if events already exist).
    seed_on_start: bool = False

    @field_validator("database_url")
    @classmethod
    def _normalize_async_db_url(cls, v: str) -> str:
        """Managed Postgres providers (Heroku, Railway, …) hand out a URL
        like ``postgres://…`` or ``postgresql://…`` with no async driver.
        asyncpg needs the ``+asyncpg`` scheme; normalise it here so the same
        env var works locally and in production. SQLite / already-qualified
        URLs are left untouched.
        """
        if v.startswith("postgres://"):
            v = "postgresql://" + v[len("postgres://"):]
        if v.startswith("postgresql://"):
            v = "postgresql+asyncpg://" + v[len("postgresql://"):]
        # asyncpg rejects libpq-style ``?sslmode=…`` query params.
        if "+asyncpg" in v and "sslmode=" in v:
            v = v.split("?", 1)[0]
        return v

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
