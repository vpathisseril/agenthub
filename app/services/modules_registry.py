"""Load modules/*/MODULE.md (front-matter + guardrail) and sync them into the DB.

MODULE.md is the single source of truth for each agent's guardrail: the
"## System guardrail" section is prepended to every run at runtime.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml
from sqlalchemy.orm import Session

from app.models import Module

MODULES_DIR = Path(__file__).resolve().parents[2] / "modules"
_FRONT = re.compile(r"^---\n(.*?)\n---\n(.*)$", re.S)


@dataclass(frozen=True)
class InputField:
    """A labelled input declared in MODULE.md front-matter (`fields:`)."""

    name: str
    label: str
    kind: str = "text"  # text | select
    placeholder: str = ""
    required: bool = False
    upload: bool = False  # allow attaching a PDF/DOCX/TXT/MD file
    rows: int = 6
    options: tuple[str, ...] = ()


def _fields(raw: Any) -> tuple[InputField, ...]:
    out = []
    for f in raw or []:
        if not isinstance(f, dict) or not re.fullmatch(r"[a-z_]{1,40}", str(f.get("name", ""))):
            raise ValueError(f"Invalid field definition: {f!r}")
        out.append(
            InputField(
                name=str(f["name"]),
                label=str(f.get("label", f["name"])),
                kind="select" if f.get("type") == "select" else "text",
                placeholder=str(f.get("placeholder", "")),
                required=bool(f.get("required", False)),
                upload=bool(f.get("upload", False)),
                rows=int(f.get("rows", 6)),
                options=tuple(str(o) for o in f.get("options", [])),
            )
        )
    return tuple(out)


@dataclass(frozen=True)
class ModuleSpec:
    id: str
    name: str
    description: str
    icon: str
    version: str
    default_provider: str
    max_tokens: int
    temperature: float
    guardrail: str
    output_format: str
    input_label: str
    input_placeholder: str
    examples: list[str] = field(default_factory=list)
    raw: str = ""
    fields: tuple[InputField, ...] = ()
    max_input_chars: int = 0  # 0 = platform default


def _section(body: str, title: str) -> str:
    m = re.search(rf"^## {re.escape(title)}[^\n]*\n(.*?)(?=^## |\Z)", body, re.S | re.M)
    return m.group(1).strip() if m else ""


def parse_module(text: str) -> ModuleSpec:
    m = _FRONT.match(text)
    if not m:
        raise ValueError("MODULE.md missing front-matter")
    meta: dict[str, Any] = yaml.safe_load(m.group(1)) or {}
    body = m.group(2)
    return ModuleSpec(
        id=str(meta["id"]),
        name=str(meta["name"]),
        description=_section(body, "Purpose"),
        icon=str(meta.get("icon", "bot")),
        version=str(meta.get("version", "1.0.0")),
        default_provider=str(meta.get("default_provider", "anthropic")),
        max_tokens=int(meta.get("max_tokens", 1000)),
        temperature=float(meta.get("temperature", 0.4)),
        guardrail=_section(body, "System guardrail"),
        output_format=_section(body, "Output format"),
        input_label=str(meta.get("input_label", "Your input")),
        input_placeholder=str(meta.get("input_placeholder", "")),
        examples=[str(x) for x in meta.get("examples", [])],
        raw=text,
        fields=_fields(meta.get("fields")),
        max_input_chars=int(meta.get("max_input_chars", 0)),
    )


@lru_cache
def load_specs() -> dict[str, ModuleSpec]:
    specs: dict[str, ModuleSpec] = {}
    for path in sorted(MODULES_DIR.glob("*/MODULE.md")):
        spec = parse_module(path.read_text(encoding="utf-8"))
        specs[spec.id] = spec
    return specs


def get_spec(module_id: str) -> ModuleSpec | None:
    return load_specs().get(module_id)


def sync_modules(db: Session) -> None:
    """Insert new modules; refresh metadata; keep admin-controlled flags."""
    for spec in load_specs().values():
        row = db.get(Module, spec.id)
        if row is None:
            db.add(
                Module(
                    id=spec.id,
                    name=spec.name,
                    description=spec.description,
                    icon=spec.icon,
                    version=spec.version,
                    max_tokens=spec.max_tokens,
                    temperature=spec.temperature,
                    default_provider=spec.default_provider,
                )
            )
        else:
            row.name, row.description, row.icon = spec.name, spec.description, spec.icon
            if row.version != spec.version:
                # A new MODULE.md version resets its limits to the new defaults.
                row.max_tokens, row.temperature = spec.max_tokens, spec.temperature
            row.version = spec.version
    db.commit()
