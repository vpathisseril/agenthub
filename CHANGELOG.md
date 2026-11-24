# Changelog
All notable changes follow [Keep a Changelog](https://keepachangelog.com) and SemVer.

## [1.1.0] - 2026-11-24
### Added
- Approval email notifications to the owner: new request (with approval instructions and SLA deadline), auto-approved FYI, SLA-breach alert. SMTP or log backend; owner email editable in Admin → Settings with a "Send test email" button. 6 new tests (72 total).

## [1.0.0] - 2026-11-24
### Added
- Deploy: `.replit` (migrations on start, Autoscale), runbook, smoke test, README with screenshots.
## [0.6.0] - 2026-11-24
### Added
- 66 tests (unit, service, API acceptance), 95% coverage; CI coverage gate, migration check; test plan and scan results.
## [0.5.0] - 2026-11-24
### Added
- Admin console: approval queue with SLA countdown, user access/caps/grants, module catalog, settings, audit log.
- Analytics: KPIs, stacked runs chart, signups, cost by provider, top users, CSV export; demo seed script.
## [0.4.0] - 2026-11-24
### Added
- LLM layer (Anthropic, OpenAI, Gemini, demo), MODULE.md registry, Agent Builder with presets, run pipeline (caps, BYOK, cache), read-only SQL sandbox, safe Markdown rendering.
### Changed
- SQL Assistant guardrail v1.1.0 (SQLite sandbox); Research Summarizer v1.1.0 (pasted text only, ADR-005).
## [0.3.0] - 2026-11-24
### Added
- Auth (argon2, sessions, CSRF, rate limits), signup with auto/manual approval and 24h SLA, RBAC, security headers, landing page, Executive Slate design system, Alembic initial migration.
## [0.2.0] - 2026-11-24
### Added
- Design (C4, ERD, sequences, route map), five ADRs, STRIDE + OWASP mapping, design tokens.
## [0.1.0] - 2026-11-24
### Added
- Requirements: personas, INVEST stories, Gherkin AC, NFRs, traceability matrix.

## [0.0.0] - 2026-11-24
### Added
- Repository skeleton (`app/`, `docs/`, `modules/`, `tests/`).
- `CLAUDE.md` master engineering guardrail.
- `modules/_TEMPLATE.md` and five starter `MODULE.md` runtime guardrails.
- FastAPI app with `/health` (reports discovered modules) and settings from env.
- CI: ruff, mypy, pytest + coverage, bandit, pip-audit, gitleaks.
- Replit config (`.replit`), `.env.example`, pre-commit hooks.
