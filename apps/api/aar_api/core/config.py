from functools import lru_cache

from pydantic import Field
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

    anthropic_api_key: str = ""
    llm_default_model: str = "claude-sonnet-4-6"
    llm_fast_model: str = "claude-haiku-4-5"
    llm_enabled: bool = False


@lru_cache
def get_settings() -> Settings:
    return Settings()
