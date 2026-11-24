"""Signup + approval workflow (auto or manual with an SLA)."""

from __future__ import annotations

from datetime import timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.security import hash_password
from app.models import Module, SignupRequest, User, UserModuleAccess, utcnow
from app.services import audit
from app.services.settings_store import get_setting


class SignupError(ValueError):
    pass


def grant_default_modules(db: Session, user: User) -> None:
    existing = {g.module_id for g in user.grants}
    defaults = db.scalars(
        select(Module).where(Module.enabled.is_(True), Module.default_for_new_users.is_(True))
    )
    for module in defaults:
        if module.id not in existing:
            user.grants.append(UserModuleAccess(module_id=module.id))


def register(db: Session, email: str, full_name: str, password: str, reason: str = "") -> User:
    email = email.strip().lower()
    if db.scalar(select(User).where(User.email == email)):
        raise SignupError("An account with this email already exists.")
    mode = get_setting(db, "approval_mode")
    cap = int(get_setting(db, "default_daily_token_cap"))
    user = User(
        email=email,
        full_name=full_name.strip()[:120],
        password_hash=hash_password(password),
        daily_token_cap=cap,
        status="pending",
    )
    db.add(user)
    db.flush()
    req = SignupRequest(user=user, reason=reason.strip()[:1000], mode=mode)
    db.add(req)
    if mode == "auto":
        _approve(db, req, actor="system:auto")
    else:
        hours = int(get_setting(db, "approval_sla_hours"))
        req.sla_due_at = utcnow() + timedelta(hours=hours)
    db.commit()
    audit.record(db, email, "signup", email, f"mode={mode}")
    return user


def _approve(db: Session, req: SignupRequest, actor: str) -> None:
    req.status = "approved"
    req.decided_at = utcnow()
    req.decided_by = actor
    req.user.status = "active"
    grant_default_modules(db, req.user)


def approve(db: Session, req: SignupRequest, actor: str) -> None:
    if req.status != "pending":
        return
    _approve(db, req, actor)
    db.commit()
    audit.record(db, actor, "signup.approve", req.user.email)


def reject(db: Session, req: SignupRequest, actor: str) -> None:
    if req.status != "pending":
        return
    req.status = "rejected"
    req.decided_at = utcnow()
    req.decided_by = actor
    req.user.status = "rejected"
    db.commit()
    audit.record(db, actor, "signup.reject", req.user.email)


def check_sla(db: Session) -> int:
    """Flag overdue pending requests; optionally auto-approve them. Returns count flagged."""
    now = utcnow()
    overdue = db.scalars(
        select(SignupRequest).where(
            SignupRequest.status == "pending",
            SignupRequest.sla_due_at.is_not(None),
            SignupRequest.sla_due_at < now,
            SignupRequest.sla_breached.is_(False),
        )
    ).all()
    auto = get_setting(db, "auto_approve_on_sla_breach") == "true"
    for req in overdue:
        req.sla_breached = True
        if auto:
            _approve(db, req, actor="system:sla-breach")
    db.commit()
    for req in overdue:
        audit.record(db, "system", "signup.sla_breach", req.user.email, f"auto_approved={auto}")
    return len(overdue)
