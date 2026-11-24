"""Typed settings loaded from environment variables (12-Factor)."""

from __future__ import annotations

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_name: str = "AgentHub"
    environment: str = "dev"  # dev | test | prod
    secret_key: str = "dev-only-change-me"  # noqa: S105 - overridden via env in prod
    fernet_key: str = ""  # base64 32-byte key; generated per process if blank (dev only)
    database_url: str = "sqlite:///./agenthub.db"

    admin_email: str = "admin@example.com"
    admin_password: str = ""  # required in production

    # Approval policy defaults (admin can change at runtime in Settings)
    approval_mode: str = "auto"  # auto | manual (initial value; admin can change)
    approval_sla_hours: int = 24
    auto_approve_on_sla_breach: bool = False

    # Notifications (approval emails to the owner)
    admin_notify_email: str = ""  # initial value; editable in Admin > Settings
    app_base_url: str = ""  # e.g. https://agenthub.replit.app (for links in emails)
    email_backend: str = "log"  # log | smtp
    smtp_host: str = "smtp.gmail.com"
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_password: str = ""
    smtp_from: str = ""

    # LLM — hybrid key model
    anthropic_api_key: str = ""
    openai_api_key: str = ""
    gemini_api_key: str = ""
    llm_fake_mode: bool = False  # force FakeProvider (demos/tests without keys)
    default_daily_token_cap: int = 50_000
    cache_ttl_seconds: int = 600

    # Default models per provider (verify current names on each vendor's site)
    anthropic_model: str = "claude-haiku-5-5"
    openai_model: str = "gpt-4o-mini"
    gemini_model: str = "gemini-2.5-flash"

    @property
    def is_production(self) -> bool:
        return self.environment in ("prod", "production")

    @property
    def sqlalchemy_url(self) -> str:
        url = self.database_url
        # Replit/Heroku style URLs -> psycopg3 driver
        if url.startswith("postgres://"):
            url = "postgresql://" + url[len("postgres://") :]
        if url.startswith("postgresql://"):
            url = "postgresql+psycopg://" + url[len("postgresql://") :]
        return url


@lru_cache
def get_settings() -> Settings:
    return Settings()
