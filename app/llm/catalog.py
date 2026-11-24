"""Model catalog: live list from each provider (key-aware, cached) with a curated fallback.

Fallback IDs were checked against the vendors' model pages in November 2026. The live
list (when a key is available) always wins, so retired names stop appearing on their own.
"""

from __future__ import annotations

import re
import time
from typing import Any

import httpx

from app.llm.providers import TIMEOUT

# First entry = cheapest capable default for that provider.
CURATED: dict[str, list[str]] = {
    "anthropic": ["claude-haiku-5-5", "claude-sonnet-5-5", "claude-opus-5-5"],
    "openai": ["gpt-6-luna", "gpt-6.1-terra", "gpt-6.1-sol", "gpt-6.2-sol"],
    "gemini": [
        "gemini-3.5-flash-lite",
        "gemini-3.5-flash",
        "gemini-3.7-flash",
        "gemini-3.1-pro-preview",
    ],
}
_SKIP = re.compile(
    r"(audio|realtime|tts|image|transcribe|embedding|search|moderation|instruct|codex|"
    r"computer|live|vision-preview|babbage|davinci|whisper|dall|sora|omni-flash|veo|imagen)",
    re.I,
)
_CACHE_TTL = 3600
_cache: dict[str, tuple[float, list[str]]] = {}


def clear_cache() -> None:
    _cache.clear()


def _fetch(provider: str, api_key: str) -> list[str]:
    if provider == "anthropic":
        r = httpx.get(
            "https://api.anthropic.com/v1/models?limit=100",
            headers={"x-api-key": api_key, "anthropic-version": "2023-06-01"},
            timeout=TIMEOUT,
        )
        r.raise_for_status()
        return [m["id"] for m in r.json().get("data", []) if "id" in m]
    if provider == "openai":
        r = httpx.get(
            "https://api.openai.com/v1/models",
            headers={"Authorization": f"Bearer {api_key}"},
            timeout=TIMEOUT,
        )
        r.raise_for_status()
        ids = [m["id"] for m in r.json().get("data", []) if "id" in m]
        ids = [
            i for i in ids if re.match(r"^(gpt-|o\d)", i) and not re.search(r"\d{4}-\d{2}-\d{2}", i)
        ]
        return sorted(ids, reverse=True)
    if provider == "gemini":
        r = httpx.get(
            "https://generativelanguage.googleapis.com/v1beta/models?pageSize=200",
            headers={"x-goog-api-key": api_key},
            timeout=TIMEOUT,
        )
        r.raise_for_status()
        data: dict[str, Any] = r.json()
        return sorted(
            (
                m["name"].removeprefix("models/")
                for m in data.get("models", [])
                if "generateContent" in m.get("supportedGenerationMethods", [])
                and m.get("name", "").startswith("models/gemini")
            ),
            reverse=True,
        )
    return []


def list_models(provider: str, api_key: str) -> tuple[list[str], bool]:
    """Return (model ids, live?). Falls back to the curated list without a key or on error."""
    curated = CURATED.get(provider, [])
    if not api_key:
        return curated, False
    key = f"{provider}:{api_key[-6:]}"
    hit = _cache.get(key)
    if hit and time.monotonic() - hit[0] < _CACHE_TTL:
        return hit[1], True
    try:
        ids = [i for i in _fetch(provider, api_key) if not _SKIP.search(i)]
    except (httpx.HTTPError, ValueError, KeyError):
        return curated, False
    if not ids:
        return curated, False
    # Curated favourites first (if the key can use them), then the rest.
    ordered = [m for m in curated if m in ids] + [m for m in ids if m not in curated]
    ordered = ordered[:40]
    _cache[key] = (time.monotonic(), ordered)
    return ordered, True
