"""AgentHub FastAPI entrypoint. Phase 0: health endpoint and module registry check only."""

from pathlib import Path

from fastapi import FastAPI

from app.core.config import get_settings

MODULES_DIR = Path(__file__).resolve().parent.parent / "modules"

settings = get_settings()
app = FastAPI(title=settings.app_name, version="0.0.0")


def discover_modules() -> list[str]:
    """Return module ids that have a MODULE.md (full registry parsing arrives in Phase 4)."""
    return sorted(p.parent.name for p in MODULES_DIR.glob("*/MODULE.md"))


@app.get("/health")
def health() -> dict[str, object]:
    return {
        "status": "ok",
        "app": settings.app_name,
        "environment": settings.environment,
        "modules": discover_modules(),
    }
