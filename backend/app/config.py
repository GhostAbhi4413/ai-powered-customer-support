"""Environment-based application configuration."""

from functools import lru_cache
from pathlib import Path
from pydantic import Field, SecretStr
from backend.app.db.database import DEFAULT_DATABASE
from backend.app.services.cancellation_policy import DEFAULT_POLICY

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="APP_", extra="ignore")

    name: str = "Assessment API"
    env: str = "development"
    database_path: Path = DEFAULT_DATABASE
    cors_origins: list[str] = ['http://localhost:5173', 'http://127.0.0.1:5173']
    return_window_days: int = Field(default=30, ge=1, le=365)
    cancellation_policy_path: Path = DEFAULT_POLICY
    gemini_api_key: SecretStr | None = Field(default=None, validation_alias='GEMINI_API_KEY')
    gemini_model: str = 'gemini-3.8-flash'
    agent_max_steps: int = Field(default=6, ge=1, le=12)


@lru_cache
def get_settings() -> Settings:
    return Settings()
