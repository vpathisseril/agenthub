"""Application settings loaded from environment variables (12-Factor)."""

from functools import lru_cache
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_name: str = "AgentHub"
    environment: Literal["dev", "test", "prod"] = "dev"
    database_url: str = "sqlite:///./agenthub.db"
    secret_key: str = "change-me"  # noqa: S105 - overridden by env in every real deployment
    fernet_key: str = ""
    admin_email: str = ""
    admin_password: str = ""

    approval_mode: Literal["auto", "manual"] = "auto"
    approval_sla_hours: int = 24
    auto_approve_on_sla_breach: bool = False

    default_daily_token_cap: int = 50_000
    anthropic_api_key: str = ""
    openai_api_key: str = ""
    gemini_api_key: str = ""


@lru_cache
def get_settings() -> Settings:
    return Settings()
