"""Application settings loaded from the environment (pydantic-settings)."""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    anthropic_api_key: str | None = None
    openai_api_key: str | None = None
    ollama_base_url: str = "http://localhost:11434"
    evalforge_db_path: str = "./evalforge.db"
    default_judge_model: str = "anthropic:claude-opus-4-8"
    generation_max_tokens: int = 1024
    judge_max_tokens: int = 1024

    # Optional shared-token auth gate. When unset/empty, the API is open (the
    # original local-tool behavior). When set, every /api request except
    # /api/health must present the token as `Authorization: Bearer <token>`
    # (or a `?token=` query param, for the plain <a href> export links).
    evalforge_api_token: str | None = None
    # Per-client request cap over a 60s sliding window; 0 disables the limiter.
    evalforge_rate_limit_per_minute: int = 120
    # When true, startup runs Alembic migrations (`upgrade head`) instead of
    # create_all — the managed-deployment path. Default false keeps the
    # zero-config local/dev/test experience.
    evalforge_use_migrations: bool = False


@lru_cache
def get_settings() -> Settings:
    return Settings()
