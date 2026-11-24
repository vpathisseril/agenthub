"""Signup, login, logout, pending status."""

from __future__ import annotations

from fastapi import APIRouter, BackgroundTasks, Depends, Form, Request
from fastapi.responses import RedirectResponse, Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.db import SessionLocal, get_db
from app.core.deps import csrf_protect, get_csrf_token, optional_user
from app.core.ratelimit import rate_limit
from app.core.security import password_problems, verify_password
from app.core.templating import flash, render
from app.models import SignupRequest, User, utcnow
from app.services import approval, audit, notify
from app.services.settings_store import get_setting

router = APIRouter(dependencies=[Depends(csrf_protect)])


def _safe_next(target: str | None) -> str:
    if target and target.startswith("/") and not target.startswith("//"):
        return target
    return "/app"


@router.get("/signup")
def signup_form(
    request: Request, db: Session = Depends(get_db), user: User | None = Depends(optional_user)
) -> Response:
    if user:
        return RedirectResponse("/app", status_code=303)
    return render(
        request, "auth/signup.html", {"mode": get_setting(db, "approval_mode"), "form": {}}
    )


def _notify_owner(user_id: int, base_url: str) -> None:
    with SessionLocal() as db:
        user = db.get(User, user_id)
        req = approval.latest_request(db, user) if user else None
        if req is not None:
            notify.notify_signup(db, req, base_url)


@router.post("/signup", dependencies=[Depends(rate_limit(5, 600))])
def signup(
    request: Request,
    background: BackgroundTasks,
    full_name: str = Form(..., max_length=120),
    email: str = Form(..., max_length=255),
    password: str = Form(..., max_length=128),
    reason: str = Form("", max_length=1000),
    db: Session = Depends(get_db),
) -> Response:
    errors = password_problems(password)
    if "@" not in email or "." not in email.split("@")[-1]:
        errors.append("Enter a valid email address.")
    if not full_name.strip():
        errors.append("Enter your name.")
    form = {"full_name": full_name, "email": email, "reason": reason}
    mode = get_setting(db, "approval_mode")
    if errors:
        return render(
            request,
            "auth/signup.html",
            {"errors": errors, "form": form, "mode": mode},
            status_code=422,
        )
    try:
        user = approval.register(db, email, full_name, password, reason)
    except approval.SignupError as exc:
        return render(
            request,
            "auth/signup.html",
            {"errors": [str(exc)], "form": form, "mode": mode},
            status_code=409,
        )
    background.add_task(_notify_owner, user.id, str(request.base_url))
    if user.status == "active":
        _start_session(request, user)
        user.last_login_at = utcnow()
        db.commit()
        flash(request, "Welcome to AgentHub — your access is approved.", "success")
        return RedirectResponse("/app", status_code=303)
    request.session["pending_email"] = user.email
    return RedirectResponse("/pending", status_code=303)


@router.get("/pending")
def pending(request: Request, db: Session = Depends(get_db)) -> Response:
    email = request.session.get("pending_email")
    req = None
    if email:
        req = db.scalar(
            select(SignupRequest)
            .join(User)
            .where(User.email == email)
            .order_by(SignupRequest.id.desc())
        )
    return render(request, "auth/pending.html", {"req": req, "now": utcnow()})


def _start_session(request: Request, user: User) -> None:
    request.session.clear()  # prevent session fixation
    request.session["uid"] = user.id
    get_csrf_token(request)


@router.get("/login")
def login_form(
    request: Request, next: str = "/app", user: User | None = Depends(optional_user)
) -> Response:
    if user:
        return RedirectResponse(_safe_next(next), status_code=303)
    return render(request, "auth/login.html", {"next": _safe_next(next)})


@router.post("/login", dependencies=[Depends(rate_limit(10, 300))])
def login(
    request: Request,
    email: str = Form(..., max_length=255),
    password: str = Form(..., max_length=128),
    next: str = Form("/app"),
    db: Session = Depends(get_db),
) -> Response:
    user = db.scalar(select(User).where(User.email == email.strip().lower()))
    if user is None or not verify_password(user.password_hash, password):
        audit.record(db, email.strip().lower()[:255], "login.failed")
        return render(
            request,
            "auth/login.html",
            {
                "errors": ["Email or password is incorrect."],
                "next": _safe_next(next),
                "email": email,
            },
            status_code=401,
        )
    if user.status == "pending":
        request.session["pending_email"] = user.email
        return RedirectResponse("/pending", status_code=303)
    if user.status != "active":
        return render(
            request,
            "auth/login.html",
            {
                "errors": ["This account is not active. Contact the administrator."],
                "next": _safe_next(next),
                "email": email,
            },
            status_code=403,
        )
    _start_session(request, user)
    user.last_login_at = utcnow()
    db.commit()
    audit.record(db, user.email, "login")
    return RedirectResponse(_safe_next(next), status_code=303)


@router.post("/logout")
def logout(request: Request) -> Response:
    request.session.clear()
    return RedirectResponse("/", status_code=303)
