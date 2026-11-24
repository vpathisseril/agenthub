"""AgentHub application factory."""

from __future__ import annotations

import asyncio
import contextlib
import logging
import time
from collections.abc import AsyncIterator, Awaitable, Callable
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from sqlalchemy import select
from sqlalchemy.exc import OperationalError
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.middleware.sessions import SessionMiddleware

from app.api import admin, auth, public, user
from app.core.config import get_settings
from app.core.db import Base, SessionLocal, engine
from app.core.deps import LoginRequired
from app.core.security import hash_password
from app.core.templating import render
from app.models import User
from app.services import approval, sample_data
from app.services.modules_registry import sync_modules

log = logging.getLogger("agenthub")
STATIC_DIR = Path(__file__).resolve().parent / "static"

CSP = (
    "default-src 'self'; img-src 'self' data:; style-src 'self'; script-src 'self'; "
    "font-src 'self'; connect-src 'self'; frame-ancestors 'none'; base-uri 'self'; "
    "form-action 'self'"
)


def bootstrap(attempts: int = 6, delay: float = 2.0) -> None:
    """Run startup tasks, retrying while a serverless Postgres wakes up or drops a connection."""
    for attempt in range(1, attempts + 1):
        try:
            _bootstrap()
            return
        except OperationalError:
            if attempt == attempts:
                raise
            log.warning("Database not ready (attempt %s/%s); retrying", attempt, attempts)
            engine.dispose()
            time.sleep(delay * attempt)


def _bootstrap() -> None:
    """Idempotent startup: tables (dev/test), modules, admin seed, sample data."""
    settings = get_settings()
    if settings.database_url.startswith("sqlite"):
        Base.metadata.create_all(engine)
    with SessionLocal() as db:
        sync_modules(db)
        if settings.admin_password and not db.scalar(
            select(User).where(User.email == settings.admin_email)
        ):
            admin_user = User(
                email=settings.admin_email.lower(),
                full_name="Administrator",
                password_hash=hash_password(settings.admin_password),
                role="admin",
                status="active",
            )
            db.add(admin_user)
            db.commit()
            db.refresh(admin_user)
            approval.grant_default_modules(db, admin_user)
            db.commit()
    sample_data.build_sample_db()


async def _sla_watch() -> None:
    while True:
        await asyncio.sleep(3600)
        try:
            with SessionLocal() as db:
                approval.check_sla(db)
        except Exception:  # pragma: no cover - keep the loop alive
            log.exception("SLA check failed")


@contextlib.asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    bootstrap()
    task = asyncio.create_task(_sla_watch())
    yield
    task.cancel()


def create_app() -> FastAPI:
    settings = get_settings()
    if settings.is_production and settings.secret_key.startswith("dev-only"):
        raise RuntimeError("SECRET_KEY must be set in production")
    app = FastAPI(title=settings.app_name, lifespan=lifespan, docs_url=None, redoc_url=None)

    @app.middleware("http")
    async def security_headers(
        request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        response = await call_next(request)
        response.headers["Content-Security-Policy"] = CSP
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
        if settings.is_production:
            response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
        return response

    app.add_middleware(
        SessionMiddleware,
        secret_key=settings.secret_key,
        session_cookie="agenthub_session",
        same_site="lax",
        https_only=settings.is_production,
        max_age=60 * 60 * 12,
    )
    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
    for router in (public.router, auth.router, user.router, admin.router):
        app.include_router(router)

    @app.exception_handler(LoginRequired)
    async def login_required(request: Request, _: LoginRequired) -> Response:
        if request.headers.get("hx-request"):
            return Response(status_code=401, headers={"HX-Redirect": "/login"})
        return RedirectResponse(f"/login?next={request.url.path}", status_code=303)

    @app.exception_handler(StarletteHTTPException)
    async def http_error(request: Request, exc: StarletteHTTPException) -> Response:
        if request.headers.get("hx-request"):
            return Response(str(exc.detail), status_code=exc.status_code)
        return render(
            request,
            "error.html",
            {"code": exc.status_code, "detail": exc.detail},
            status_code=exc.status_code,
        )

    return app


app = create_app()
