"""Application configuration via pydantic-settings."""
from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # Database
    database_url: str = "postgresql://postgres:postgres@localhost:5432/santhosh_db"
    db_min_pool: int = 2
    db_max_pool: int = 10
    db_command_timeout: int = 30

    # Gemini
    gemini_api_key: str = ""
    gemini_model: str = "gemini-1.5-pro"
    gemini_max_tokens: int = 2048
    gemini_temperature: float = 0.1
    gemini_retry_attempts: int = 3
    gemini_retry_delay: float = 1.0

    # Pipeline
    max_query_length: int = 500
    max_result_rows: int = 1000      # Hard cap — enforced in executor, NOT LLM
    default_limit: int = 100         # Default LIMIT injected by executor
    schema_cache_ttl: int = 300      # seconds
    ambiguity_min_words: int = 3
    fuzzy_match_threshold: float = 0.3
    confidence_warn_threshold: float = 0.6
    confidence_block_threshold: float = 0.3

    # Session
    session_max_history: int = 10

    # Logging
    log_level: str = "INFO"
    log_format: str = "json"        # "json" or "text"

    # App
    app_env: str = "development"    # "development" or "production"


@lru_cache
def get_settings() -> Settings:
    return Settings()
