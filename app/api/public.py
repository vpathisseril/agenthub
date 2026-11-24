"""Public pages: landing, health."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from fastapi.responses import Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.db import get_db
from app.core.deps import optional_user
from app.core.templating import render
from app.models import Module, User
from app.services.modules_registry import load_specs

router = APIRouter()


@router.get("/", include_in_schema=False)
def landing(
    request: Request, db: Session = Depends(get_db), user: User | None = Depends(optional_user)
) -> Response:
    modules = db.scalars(select(Module).where(Module.enabled.is_(True)).order_by(Module.name)).all()
    return render(request, "landing.html", {"modules": modules, "user": user})


@router.get("/health")
def health() -> dict[str, object]:
    return {
        "status": "ok",
        "app": get_settings().app_name,
        "environment": get_settings().environment,
        "modules": sorted(load_specs()),
    }
