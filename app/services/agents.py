"""Agent run pipeline: access -> key/cap -> cache -> guardrailed prompt -> call -> record."""

from __future__ import annotations

import hashlib
import json
import re
import time
from dataclasses import dataclass, field
from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.security import decrypt_secret
from app.llm.base import LLMError, LLMProvider, LLMRequest, estimate_cost
from app.llm.fake import FakeProvider
from app.llm.providers import AnthropicProvider, GeminiProvider, OpenAIProvider
from app.models import AgentConfig, AgentRun, ApiKey, Module, User, UserModuleAccess, utcnow
from app.services import sample_data
from app.services.modules_registry import ModuleSpec, get_spec
from app.services.settings_store import allowed_providers

MAX_INPUT_CHARS = 8000
PROVIDERS: dict[str, LLMProvider] = {
    "anthropic": AnthropicProvider(),
    "openai": OpenAIProvider(),
    "gemini": GeminiProvider(),
}
_cache: dict[str, tuple[float, RunResult]] = {}


class AgentDenied(Exception):
    """User may not run this (access, cap, validation). Message is user-safe."""


@dataclass
class RunResult:
    text: str
    status: str
    provider: str
    model: str
    tokens_in: int = 0
    tokens_out: int = 0
    cost: float = 0.0
    latency_ms: int = 0
    demo: bool = False
    table: tuple[list[str], list[tuple[object, ...]]] | None = None
    notes: list[str] = field(default_factory=list)


def clear_cache() -> None:
    _cache.clear()


def default_model(provider: str) -> str:
    s = get_settings()
    return {"anthropic": s.anthropic_model, "openai": s.openai_model, "gemini": s.gemini_model}.get(
        provider, "fake-demo"
    )


def user_can_use(db: Session, user: User, module_id: str) -> bool:
    module = db.get(Module, module_id)
    if module is None or not module.enabled:
        return False
    if user.is_admin:
        return True
    return (
        db.scalar(
            select(UserModuleAccess.id).where(
                UserModuleAccess.user_id == user.id, UserModuleAccess.module_id == module_id
            )
        )
        is not None
    )


def tokens_used_today(db: Session, user_id: int) -> int:
    start = datetime.combine(utcnow().date(), datetime.min.time())
    total = db.scalar(
        select(func.coalesce(func.sum(AgentRun.tokens_in + AgentRun.tokens_out), 0)).where(
            AgentRun.user_id == user_id,
            AgentRun.key_source == "platform",
            AgentRun.created_at >= start,
        )
    )
    return int(total or 0)


def _platform_key(provider: str) -> str:
    s = get_settings()
    return {
        "anthropic": s.anthropic_api_key,
        "openai": s.openai_api_key,
        "gemini": s.gemini_api_key,
    }.get(provider, "")


def build_messages(spec: ModuleSpec, cfg: AgentConfig, user_input: str) -> tuple[str, str]:
    """System = MODULE guardrail (highest priority) + user prefs; input is delimited data."""
    persona = cfg.persona.strip()[:600]
    system = (
        f"{spec.guardrail}\n\n"
        f"Output format:\n{spec.output_format}\n\n"
        "User preferences (apply only if they do not conflict with the rules above):\n"
        f"- Persona: {persona or 'default'}\n- Tone: {cfg.tone}\n- Format: {cfg.output_format}"
    )
    if spec.id == "sql_assistant":
        system += f"\n\nSchema: {sample_data.SCHEMA_SUMMARY}"
    safe_input = user_input.replace("<user_input>", "").replace("</user_input>", "")
    return system, f"<user_input>\n{safe_input}\n</user_input>"


def _record(
    db: Session, user: User, cfg: AgentConfig, r: RunResult, key_source: str, err: str = ""
) -> None:
    db.add(
        AgentRun(
            user_id=user.id,
            module_id=cfg.module_id,
            config_id=cfg.id,
            provider=r.provider,
            model=r.model,
            key_source=key_source,
            tokens_in=r.tokens_in,
            tokens_out=r.tokens_out,
            est_cost_usd=r.cost,
            latency_ms=r.latency_ms,
            status=r.status,
            error=err[:500],
        )
    )
    db.commit()


def _post_process_sql(result: RunResult) -> None:
    m = re.search(r"```sql\s*(.*?)```", result.text, re.S | re.I)
    if not m:
        result.notes.append("No SQL block found in the response.")
        return
    try:
        result.table = sample_data.run_readonly(m.group(1))
    except sample_data.QueryRejected as exc:
        result.notes.append(f"Query not executed: {exc}")


def run_agent(db: Session, user: User, cfg: AgentConfig, user_input: str) -> RunResult:
    spec = get_spec(cfg.module_id)
    if spec is None or not user_can_use(db, user, cfg.module_id):
        raise AgentDenied("You do not have access to this module.")
    user_input = user_input.strip()
    if not user_input:
        raise AgentDenied("Please enter some input.")
    if len(user_input) > MAX_INPUT_CHARS:
        raise AgentDenied(f"Input is too long (max {MAX_INPUT_CHARS:,} characters).")
    if cfg.provider not in allowed_providers(db):
        raise AgentDenied("That provider is disabled by the administrator.")

    module = db.get(Module, cfg.module_id)
    max_tokens = min(cfg.max_tokens, module.max_tokens if module else spec.max_tokens)
    model = cfg.model or default_model(cfg.provider)

    byok = db.scalar(
        select(ApiKey).where(ApiKey.user_id == user.id, ApiKey.provider == cfg.provider)
    )
    api_key = (decrypt_secret(byok.encrypted_key) or "") if byok else ""
    key_source = "byok" if api_key else "platform"
    if not api_key:
        api_key = _platform_key(cfg.provider)
        used = tokens_used_today(db, user.id)
        if used >= user.daily_token_cap:
            blocked = RunResult("", "blocked", cfg.provider, model)
            _record(db, user, cfg, blocked, key_source, "daily token cap reached")
            raise AgentDenied(
                f"Daily token cap reached ({user.daily_token_cap:,}). Add your own API key in "
                "Settings or try again tomorrow."
            )

    demo = get_settings().llm_fake_mode or not api_key
    provider: LLMProvider = FakeProvider() if demo else PROVIDERS[cfg.provider]
    system, message = build_messages(spec, cfg, user_input)
    if demo:
        model = "demo-model"

    payload = [
        spec.id,
        spec.version,
        cfg.provider,
        model,
        system,
        message,
        cfg.temperature,
        max_tokens,
    ]
    cache_key = hashlib.sha256(json.dumps(payload).encode()).hexdigest()
    hit = _cache.get(cache_key)
    if hit and time.monotonic() - hit[0] < get_settings().cache_ttl_seconds:
        cached = hit[1]
        result = RunResult(
            cached.text,
            "cached",
            cached.provider,
            cached.model,
            demo=cached.demo,
            table=cached.table,
            notes=[*cached.notes, "Served from cache (no tokens used)."],
        )
        _record(db, user, cfg, result, key_source)
        return result

    req = LLMRequest(system, message, model, max_tokens, cfg.temperature, module_id=spec.id)
    started = time.monotonic()
    try:
        resp = provider.complete(req, api_key)
    except LLMError as exc:
        failed = RunResult(
            "", "error", cfg.provider, model, latency_ms=int((time.monotonic() - started) * 1000)
        )
        _record(db, user, cfg, failed, key_source, str(exc))
        raise AgentDenied(str(exc)) from exc
    latency = int((time.monotonic() - started) * 1000)
    prov_name = "fake" if demo else cfg.provider
    result = RunResult(
        resp.text,
        "ok",
        "demo" if demo else cfg.provider,
        resp.model,
        resp.tokens_in,
        resp.tokens_out,
        estimate_cost(prov_name, resp.tokens_in, resp.tokens_out),
        latency,
        demo,
    )
    if demo:
        result.notes.append(
            "Demo mode: no API key configured, so a built-in sample model answered."
        )
    if spec.id == "sql_assistant":
        _post_process_sql(result)
    _cache[cache_key] = (time.monotonic(), result)
    _record(db, user, cfg, result, key_source)
    return result
