"""Request dependencies: current user, RBAC, CSRF."""

from __future__ import annotations

from collections.abc import Callable

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.core.security import csrf_matches, new_csrf_token
from app.models import User


class LoginRequired(Exception):
    """Raised for anonymous access to protected pages; handled as a redirect."""


def get_csrf_token(request: Request) -> str:
    token = request.session.get("csrf")
    if not token:
        token = new_csrf_token()
        request.session["csrf"] = token
    return str(token)


async def csrf_protect(request: Request) -> None:
    """Validate CSRF on unsafe methods (form field or HTMX header)."""
    if request.method in ("GET", "HEAD", "OPTIONS"):
        return
    provided = request.headers.get("x-csrf-token")
    if not provided:
        form = await request.form()
        value = form.get("csrf_token")
        provided = value if isinstance(value, str) else None
    if not csrf_matches(request.session.get("csrf"), provided):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Invalid or missing CSRF token")


def optional_user(request: Request, db: Session = Depends(get_db)) -> User | None:
    uid = request.session.get("uid")
    if not uid:
        return None
    user = db.get(User, int(uid))
    if user is None or user.status != "active":
        request.session.pop("uid", None)
        return None
    return user


def current_user(user: User | None = Depends(optional_user)) -> User:
    if user is None:
        raise LoginRequired()
    return user


def require_role(role: str) -> Callable[[User], User]:
    def checker(user: User = Depends(current_user)) -> User:
        if user.role != role:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "You do not have access to this area")
        return user

    return checker


require_admin = require_role("admin")
