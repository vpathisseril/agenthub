"""Runtime settings that admins can change (stored in the settings table)."""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models import Setting

DEFAULTS: dict[str, str] = {
    "approval_mode": get_settings().approval_mode,
    "approval_sla_hours": str(get_settings().approval_sla_hours),
    "auto_approve_on_sla_breach": "true" if get_settings().auto_approve_on_sla_breach else "false",
    "default_daily_token_cap": str(get_settings().default_daily_token_cap),
    "allowed_providers": "anthropic,openai,gemini",
    "notify_email": get_settings().admin_notify_email,
}


def get_setting(db: Session, key: str) -> str:
    row = db.get(Setting, key)
    return row.value if row else DEFAULTS.get(key, "")


def set_setting(db: Session, key: str, value: str) -> None:
    row = db.get(Setting, key)
    if row:
        row.value = value
    else:
        db.add(Setting(key=key, value=value))
    db.commit()


def allowed_providers(db: Session) -> list[str]:
    return [p for p in get_setting(db, "allowed_providers").split(",") if p]
