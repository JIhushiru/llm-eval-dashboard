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


@lru_cache
def get_settings() -> Settings:
    return Settings()
