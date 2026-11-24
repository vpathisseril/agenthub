"""Admin console: users & access, modules, settings, analytics, audit."""

from __future__ import annotations

import csv
import io
import json

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import RedirectResponse, Response
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.db import get_db
from app.core.deps import csrf_protect, require_admin
from app.core.templating import flash, render
from app.models import AuditLog, Module, SignupRequest, User, UserModuleAccess, utcnow
from app.services import agents, analytics, approval, audit, notify
from app.services.modules_registry import get_spec
from app.services.settings_store import get_setting, set_setting

router = APIRouter(prefix="/admin", dependencies=[Depends(csrf_protect), Depends(require_admin)])


def _nav(db: Session) -> list[Module]:
    return list(db.scalars(select(Module).where(Module.enabled.is_(True)).order_by(Module.name)))


@router.get("")
def dashboard(
    request: Request,
    days: int = 30,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> Response:
    days = days if days in (7, 30, 90) else 30
    approval.check_sla(db)
    data = analytics.dashboard(db, days)
    return render(
        request,
        "admin/dashboard.html",
        {
            "user": admin,
            "nav_modules": _nav(db),
            "data": data,
            "chart_json": json.dumps(data),
            "days": days,
            "as_of": analytics.as_of(),
        },
    )


@router.get("/analytics.csv")
def export_csv(days: int = 30, db: Session = Depends(get_db)) -> Response:
    buf = io.StringIO()
    csv.writer(buf).writerows(analytics.runs_csv_rows(db, days if days in (7, 30, 90) else 30))
    return Response(
        buf.getvalue(),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename=agenthub-runs-{days}d.csv"},
    )


@router.get("/users")
def users(
    request: Request,
    q: str = "",
    status: str = "",
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> Response:
    approval.check_sla(db)
    stmt = select(User).order_by(User.created_at.desc())
    if q:
        stmt = stmt.where(or_(User.email.ilike(f"%{q}%"), User.full_name.ilike(f"%{q}%")))
    if status:
        stmt = stmt.where(User.status == status)
    rows = db.scalars(stmt.limit(200)).all()
    pending = db.scalars(
        select(SignupRequest)
        .where(SignupRequest.status == "pending")
        .order_by(SignupRequest.requested_at)
    ).all()
    modules = db.scalars(select(Module).order_by(Module.name)).all()
    grants = {(g.user_id, g.module_id) for g in db.scalars(select(UserModuleAccess))}
    usage = {u.id: agents.tokens_used_today(db, u.id) for u in rows}
    return render(
        request,
        "admin/users.html",
        {
            "user": admin,
            "nav_modules": _nav(db),
            "rows": rows,
            "pending": pending,
            "modules": modules,
            "grants": grants,
            "usage": usage,
            "q": q,
            "status": status,
            "now": utcnow(),
        },
    )


def _request_or_404(db: Session, req_id: int) -> SignupRequest:
    req = db.get(SignupRequest, req_id)
    if req is None:
        raise HTTPException(404, "Request not found")
    return req


@router.post("/requests/{req_id}/approve")
def approve(
    request: Request,
    req_id: int,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> Response:
    req = _request_or_404(db, req_id)
    approval.approve(db, req, admin.email)
    flash(request, f"Approved {req.user.email}.", "success")
    return RedirectResponse("/admin/users", status_code=303)


@router.post("/requests/{req_id}/reject")
def reject(
    request: Request,
    req_id: int,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> Response:
    req = _request_or_404(db, req_id)
    approval.reject(db, req, admin.email)
    flash(request, f"Rejected {req.user.email}.", "info")
    return RedirectResponse("/admin/users", status_code=303)


@router.post("/users/{user_id}")
async def update_user(
    request: Request,
    user_id: int,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> Response:
    target = db.get(User, user_id)
    if target is None:
        raise HTTPException(404, "User not found")
    form = await request.form()
    changes = []
    status = str(form.get("status", target.status))
    role = str(form.get("role", target.role))
    if target.id == admin.id and (status != "active" or role != "admin"):
        flash(request, "You cannot suspend or demote your own account.", "error")
        return RedirectResponse("/admin/users", status_code=303)
    if status in ("active", "suspended") and status != target.status:
        changes.append(f"status {target.status}->{status}")
        target.status = status
    if role in ("user", "admin") and role != target.role:
        changes.append(f"role {target.role}->{role}")
        target.role = role
    cap_raw = str(form.get("daily_token_cap", target.daily_token_cap))
    if cap_raw.isdigit() and int(cap_raw) != target.daily_token_cap:
        changes.append(f"cap {target.daily_token_cap}->{cap_raw}")
        target.daily_token_cap = min(int(cap_raw), 10_000_000)
    wanted = {str(v) for v in form.getlist("modules")}
    have = {g.module_id for g in target.grants}
    valid = {m.id for m in db.scalars(select(Module))}
    for mid in (wanted - have) & valid:
        db.add(UserModuleAccess(user_id=target.id, module_id=mid))
        changes.append(f"+{mid}")
    for g in list(target.grants):
        if g.module_id not in wanted:
            db.delete(g)
            changes.append(f"-{g.module_id}")
    db.commit()
    if changes:
        audit.record(db, admin.email, "user.update", target.email, ", ".join(changes))
        flash(request, f"Updated {target.email}: {', '.join(changes)}.", "success")
    return RedirectResponse("/admin/users", status_code=303)


@router.get("/modules")
def modules(
    request: Request, admin: User = Depends(require_admin), db: Session = Depends(get_db)
) -> Response:
    rows = db.scalars(select(Module).order_by(Module.name)).all()
    counts = {
        m.id: len(
            db.scalars(select(UserModuleAccess.id).where(UserModuleAccess.module_id == m.id)).all()
        )
        for m in rows
    }
    return render(
        request,
        "admin/modules.html",
        {
            "user": admin,
            "nav_modules": _nav(db),
            "rows": rows,
            "counts": counts,
            "specs": {m.id: get_spec(m.id) for m in rows},
        },
    )


@router.post("/modules/{module_id}")
def update_module(
    request: Request,
    module_id: str,
    enabled: str = Form(""),
    default_for_new_users: str = Form(""),
    max_tokens: int = Form(..., ge=50, le=8000),
    temperature: float = Form(..., ge=0, le=1),
    default_provider: str = Form(...),
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> Response:
    module = db.get(Module, module_id)
    if module is None:
        raise HTTPException(404, "Module not found")
    module.enabled = bool(enabled)
    module.default_for_new_users = bool(default_for_new_users)
    module.max_tokens, module.temperature = max_tokens, round(temperature, 2)
    if default_provider in ("anthropic", "openai", "gemini"):
        module.default_provider = default_provider
    db.commit()
    audit.record(
        db,
        admin.email,
        "module.update",
        module_id,
        f"enabled={module.enabled} max_tokens={max_tokens} temp={temperature}",
    )
    flash(request, f"Saved {module.name}.", "success")
    return RedirectResponse("/admin/modules", status_code=303)


@router.get("/settings")
def settings_page(
    request: Request, admin: User = Depends(require_admin), db: Session = Depends(get_db)
) -> Response:
    keys = (
        "approval_mode",
        "approval_sla_hours",
        "auto_approve_on_sla_breach",
        "default_daily_token_cap",
        "allowed_providers",
        "notify_email",
    )
    return render(
        request,
        "admin/settings.html",
        {
            "user": admin,
            "nav_modules": _nav(db),
            "s": {k: get_setting(db, k) for k in keys},
            "email_backend": get_settings().email_backend,
        },
    )


@router.post("/settings")
async def save_settings(
    request: Request, admin: User = Depends(require_admin), db: Session = Depends(get_db)
) -> Response:
    form = await request.form()
    mode = str(form.get("approval_mode", "auto"))
    sla = str(form.get("approval_sla_hours", "24"))
    cap = str(form.get("default_daily_token_cap", "50000"))
    providers = [
        p for p in form.getlist("allowed_providers") if p in ("anthropic", "openai", "gemini")
    ]
    notify_to = str(form.get("notify_email", "")).strip()
    bad_email = bool(notify_to) and not notify.EMAIL_RE.match(notify_to)
    if (
        mode not in ("auto", "manual")
        or not sla.isdigit()
        or not cap.isdigit()
        or not providers
        or bad_email
    ):
        flash(
            request,
            "Check the values: SLA and cap must be numbers, one provider must be on, "
            "and the notification email must be valid.",
            "error",
        )
        return RedirectResponse("/admin/settings", status_code=303)
    new = {
        "approval_mode": mode,
        "approval_sla_hours": str(max(1, min(int(sla), 168))),
        "auto_approve_on_sla_breach": "true" if form.get("auto_approve_on_sla_breach") else "false",
        "default_daily_token_cap": cap,
        "allowed_providers": ",".join(str(p) for p in providers),
        "notify_email": notify_to,
    }
    for k, v in new.items():
        set_setting(db, k, v)
    audit.record(db, admin.email, "settings.update", "", json.dumps(new))
    flash(request, "Settings saved.", "success")
    return RedirectResponse("/admin/settings", status_code=303)


@router.post("/settings/test-email")
def test_email(
    request: Request, admin: User = Depends(require_admin), db: Session = Depends(get_db)
) -> Response:
    to = notify.owner_email(db)
    if not notify.EMAIL_RE.match(to):
        flash(request, "Set an approval notification email first.", "error")
        return RedirectResponse("/admin/settings", status_code=303)
    ok = notify.send_email(
        to,
        "[AgentHub] Test notification",
        "This is a test from AgentHub. Approval requests will arrive at this address.\n\n"
        + notify._instructions(str(request.base_url).rstrip("/")),
    )
    audit.record(db, admin.email, "settings.test_email", to, f"ok={ok}")
    backend = get_settings().email_backend
    if ok and backend == "smtp":
        flash(request, f"Test email sent to {to}.", "success")
    elif ok:
        flash(
            request,
            "Email is in log-only mode: the message was written to the app log. "
            "Set EMAIL_BACKEND=smtp and SMTP secrets to deliver real email.",
            "info",
        )
    else:
        flash(request, "Sending failed. Check the SMTP secrets and the app log.", "error")
    return RedirectResponse("/admin/settings", status_code=303)


@router.get("/audit")
def audit_log(
    request: Request,
    action: str = "",
    actor: str = "",
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> Response:
    stmt = select(AuditLog).order_by(AuditLog.id.desc())
    if action:
        stmt = stmt.where(AuditLog.action.ilike(f"{action}%"))
    if actor:
        stmt = stmt.where(AuditLog.actor.ilike(f"%{actor}%"))
    rows = db.scalars(stmt.limit(300)).all()
    actions = sorted({a for a in db.scalars(select(AuditLog.action).distinct())})
    return render(
        request,
        "admin/audit.html",
        {
            "user": admin,
            "nav_modules": _nav(db),
            "rows": rows,
            "action": action,
            "actor": actor,
            "actions": actions,
        },
    )
