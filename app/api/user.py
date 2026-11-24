"""Signed-in user area: module gallery, agent builder, runs, BYOK settings."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import RedirectResponse, Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.core.deps import csrf_protect, current_user
from app.core.ratelimit import rate_limit
from app.core.security import encrypt_secret
from app.core.templating import flash, render
from app.models import AgentConfig, AgentRun, ApiKey, Module, User
from app.services import agents, audit
from app.services.markdown_lite import render_markdown
from app.services.modules_registry import get_spec
from app.services.settings_store import allowed_providers

router = APIRouter(prefix="/app", dependencies=[Depends(csrf_protect)])
TONES = ["professional", "executive", "concise", "friendly", "technical"]
FORMATS = ["markdown", "bullets", "table", "narrative"]


def _my_modules(db: Session, user: User) -> list[Module]:
    mods = db.scalars(select(Module).where(Module.enabled.is_(True)).order_by(Module.name)).all()
    return [m for m in mods if agents.user_can_use(db, user, m.id)]


@router.get("")
def home(
    request: Request, user: User = Depends(current_user), db: Session = Depends(get_db)
) -> Response:
    runs = db.scalars(
        select(AgentRun).where(AgentRun.user_id == user.id).order_by(AgentRun.id.desc()).limit(8)
    ).all()
    used = agents.tokens_used_today(db, user.id)
    names = {m.id: m.name for m in db.scalars(select(Module))}
    return render(
        request,
        "app/home.html",
        {
            "user": user,
            "modules": _my_modules(db, user),
            "nav_modules": _my_modules(db, user),
            "runs": runs,
            "names": names,
            "used": used,
            "cap": user.daily_token_cap,
            "pct": min(100, round(100 * used / user.daily_token_cap))
            if user.daily_token_cap
            else 0,
            "byok": [
                k.provider for k in db.scalars(select(ApiKey).where(ApiKey.user_id == user.id))
            ],
        },
    )


def _config_for(db: Session, user: User, module: Module, config_id: int | None) -> AgentConfig:
    if config_id:
        cfg = db.get(AgentConfig, config_id)
        if cfg and cfg.user_id == user.id and cfg.module_id == module.id:
            return cfg
    cfg = db.scalar(
        select(AgentConfig)
        .where(AgentConfig.user_id == user.id, AgentConfig.module_id == module.id)
        .order_by(AgentConfig.id)
    )
    if cfg:
        return cfg
    cfg = AgentConfig(
        user_id=user.id,
        module_id=module.id,
        name="Default",
        provider=module.default_provider,
        temperature=module.temperature,
        max_tokens=module.max_tokens,
    )
    db.add(cfg)
    db.commit()
    return cfg


def _module_or_403(db: Session, user: User, module_id: str) -> Module:
    module = db.get(Module, module_id)
    if module is None or not agents.user_can_use(db, user, module_id):
        raise HTTPException(403, "You do not have access to this module")
    return module


@router.get("/modules/{module_id}")
def builder(
    request: Request,
    module_id: str,
    config: int | None = None,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> Response:
    module = _module_or_403(db, user, module_id)
    cfg = _config_for(db, user, module, config)
    configs = db.scalars(
        select(AgentConfig)
        .where(AgentConfig.user_id == user.id, AgentConfig.module_id == module.id)
        .order_by(AgentConfig.id)
    ).all()
    return render(
        request,
        "app/builder.html",
        {
            "user": user,
            "module": module,
            "spec": get_spec(module_id),
            "cfg": cfg,
            "configs": configs,
            "providers": allowed_providers(db),
            "tones": TONES,
            "formats": FORMATS,
            "default_models": {
                p: agents.default_model(p) for p in ("anthropic", "openai", "gemini")
            },
            "nav_modules": _my_modules(db, user),
        },
    )


@router.post("/modules/{module_id}/config")
def save_config(
    request: Request,
    module_id: str,
    config_id: int = Form(0),
    name: str = Form("Default", max_length=80),
    provider: str = Form(...),
    model: str = Form("", max_length=80),
    persona: str = Form("", max_length=600),
    tone: str = Form("professional"),
    output_format: str = Form("markdown"),
    temperature: float = Form(0.4, ge=0, le=1),
    max_tokens: int = Form(800, ge=50, le=4000),
    save_as_new: str = Form(""),
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> Response:
    module = _module_or_403(db, user, module_id)
    if provider not in allowed_providers(db):
        raise HTTPException(400, "Provider not allowed")
    cfg = None if save_as_new else db.get(AgentConfig, config_id)
    if cfg is None or cfg.user_id != user.id:
        cfg = AgentConfig(user_id=user.id, module_id=module.id)
        db.add(cfg)
    cfg.name = name.strip() or "Untitled"
    cfg.provider, cfg.model, cfg.persona = provider, model.strip(), persona.strip()
    cfg.tone = tone if tone in TONES else "professional"
    cfg.output_format = output_format if output_format in FORMATS else "markdown"
    cfg.temperature = round(temperature, 2)
    cfg.max_tokens = min(max_tokens, module.max_tokens)
    db.commit()
    flash(request, f"Saved agent “{cfg.name}”.", "success")
    return RedirectResponse(f"/app/modules/{module.id}?config={cfg.id}", status_code=303)


@router.post("/modules/{module_id}/run", dependencies=[Depends(rate_limit(20, 60))])
def run(
    request: Request,
    module_id: str,
    config_id: int = Form(...),
    user_input: str = Form(..., max_length=20000),
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> Response:
    module = _module_or_403(db, user, module_id)
    cfg = _config_for(db, user, module, config_id)
    try:
        result = agents.run_agent(db, user, cfg, user_input)
    except agents.AgentDenied as exc:
        return render(request, "partials/run_result.html", {"error": str(exc)})
    return render(
        request,
        "partials/run_result.html",
        {
            "result": result,
            "html": render_markdown(result.text),
            "used": agents.tokens_used_today(db, user.id),
            "cap": user.daily_token_cap,
        },
    )


@router.get("/settings")
def settings_page(
    request: Request, user: User = Depends(current_user), db: Session = Depends(get_db)
) -> Response:
    keys = db.scalars(select(ApiKey).where(ApiKey.user_id == user.id)).all()
    return render(
        request,
        "app/settings.html",
        {
            "user": user,
            "keys": keys,
            "providers": ["anthropic", "openai", "gemini"],
            "nav_modules": _my_modules(db, user),
        },
    )


@router.post("/settings/keys")
def save_key(
    request: Request,
    provider: str = Form(...),
    api_key: str = Form(..., min_length=8, max_length=300),
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> Response:
    if provider not in ("anthropic", "openai", "gemini"):
        raise HTTPException(400, "Unknown provider")
    key = api_key.strip()
    row = db.scalar(select(ApiKey).where(ApiKey.user_id == user.id, ApiKey.provider == provider))
    if row is None:
        row = ApiKey(user_id=user.id, provider=provider, encrypted_key="", last4="")
        db.add(row)
    row.encrypted_key, row.last4 = encrypt_secret(key), key[-4:]
    db.commit()
    audit.record(db, user.email, "byok.save", provider)
    flash(request, f"Saved your {provider.title()} key (ending …{row.last4}).", "success")
    return RedirectResponse("/app/settings", status_code=303)


@router.post("/settings/keys/{provider}/delete")
def delete_key(
    request: Request,
    provider: str,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
) -> Response:
    row = db.scalar(select(ApiKey).where(ApiKey.user_id == user.id, ApiKey.provider == provider))
    if row:
        db.delete(row)
        db.commit()
        audit.record(db, user.email, "byok.delete", provider)
        flash(request, f"Removed your {provider.title()} key.", "info")
    return RedirectResponse("/app/settings", status_code=303)
