"""Append-only audit trail for admin actions and security events."""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.models import AuditLog


def record(db: Session, actor: str, action: str, target: str = "", detail: str = "") -> None:
    db.add(AuditLog(actor=actor, action=action, target=target, detail=detail[:2000]))
    db.commit()
