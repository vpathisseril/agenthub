# Changelog
All notable changes follow [Keep a Changelog](https://keepachangelog.com) and SemVer.

## [0.0.0] - 2026-11-24
### Added
- Repository skeleton (`app/`, `docs/`, `modules/`, `tests/`).
- `CLAUDE.md` master engineering guardrail.
- `modules/_TEMPLATE.md` and five starter `MODULE.md` runtime guardrails.
- FastAPI app with `/health` (reports discovered modules) and settings from env.
- CI: ruff, mypy, pytest + coverage, bandit, pip-audit, gitleaks.
- Replit config (`.replit`), `.env.example`, pre-commit hooks.
