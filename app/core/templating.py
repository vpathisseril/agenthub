"""Jinja2 templates with shared context (CSRF, flash messages, user)."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from fastapi import Request
from fastapi.templating import Jinja2Templates
from markupsafe import Markup
from starlette.responses import Response

from app.core.config import get_settings
from app.core.deps import get_csrf_token

TEMPLATE_DIR = Path(__file__).resolve().parent.parent / "templates"
templates = Jinja2Templates(directory=str(TEMPLATE_DIR))
_ICON_NAME = re.compile(r"^[a-z0-9-]+$")


def icon(name: str, cls: str = "icon") -> Markup:
    """Lucide icon from the local SVG sprite."""
    if not _ICON_NAME.match(name) or not _ICON_NAME.match(cls.replace(" ", "-")):
        name = "bot"
    return Markup(  # noqa: S704  # nosec B704
        f'<svg class="{cls}" aria-hidden="true"><use href="/static/icons/sprite.svg#{name}"></use></svg>'
    )


def fmt_int(value: int | float | None) -> str:
    return "—" if value is None else f"{value:,.0f}"


templates.env.globals["icon"] = icon
templates.env.filters["n"] = fmt_int


def flash(request: Request, message: str, kind: str = "info") -> None:
    msgs = request.session.setdefault("flash", [])
    msgs.append({"message": message, "kind": kind})
    request.session["flash"] = msgs


def render(
    request: Request, name: str, context: dict[str, Any] | None = None, status_code: int = 200
) -> Response:
    ctx: dict[str, Any] = {
        "csrf_token": get_csrf_token(request),
        "flashes": request.session.pop("flash", []),
        "app_name": get_settings().app_name,
        "path": request.url.path,
    }
    ctx.update(context or {})
    return templates.TemplateResponse(request, name, ctx, status_code=status_code)
