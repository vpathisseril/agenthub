# AgentHub — Engineering Guardrails (master)

> Always loaded by Claude Code. Keep under ~120 lines. Module-specific rules live in
> `modules/<id>/MODULE.md` and are loaded only when that module is in play.

## Mission
Portfolio-grade AI agent platform: governed signup, module-based access, user-configured
agents, admin console with reporting & analytics. Deployed GitHub -> Replit.
Optimize for: security > correctness > clarity > speed.

## Locked stack
Python 3.12, FastAPI, SQLAlchemy 2 + Alembic, Postgres (SQLite for tests only),
Jinja2 + HTMX + Alpine.js, Tailwind CSS (standalone CLI), Lucide icons, argon2,
itsdangerous sessions, pytest, ruff, mypy, bandit, pip-audit, gitleaks, GitHub Actions.
LLM providers: Anthropic, OpenAI, Gemini behind one `LLMProvider` protocol.
Keys: hybrid — platform key with per-user daily token caps, or user BYOK (Fernet-encrypted).

## How you work (phase protocol)
- Work strictly phase by phase (see README "Phases"). One phase = one branch = one PR = one tag `v0.N`.
- End of every phase: run checks, summarize in <= 10 bullets, print the AC table
  (ID | criterion | PASS/FAIL), propose a conventional-commit message, then STOP.
- When uncertain, ask one precise question instead of guessing.

## Token budget rules (for the coding agent)
- Read only files relevant to the current phase; `grep` before opening files.
- Never paste whole files back; show diffs or changed functions only.
- Do not restate requirements already given. Summaries <= 10 bullets.
- Load `modules/<x>/MODULE.md` only when touching module `<x>`.

## Code standards
- Type hints everywhere; `ruff` + `mypy --strict` on `app/`; max file 300 lines.
- Layering: `api -> services -> models`; no DB calls in routes or templates.
- Config only via env (`app/core/config.py`), documented in `.env.example` (12-Factor).
- Conventional Commits; SemVer tags; CHANGELOG entry per phase.

## Security (non-negotiable)
- Secrets only from env; `.env` never committed; pre-commit runs gitleaks.
- argon2 password hashing; CSRF on all forms; cookies secure + httponly + samesite=lax.
- RBAC via a FastAPI dependency (`require_role`), never inline checks.
- Rate-limit auth and agent-run routes. Security headers: CSP, HSTS, X-Frame-Options, nosniff.
- Treat all LLM output as untrusted: autoescape in templates; never exec/eval it.
- Prompt-injection defense: MODULE.md system guardrail always prepended; user content
  wrapped in `<user_input>...</user_input>`; tools allow-listed per module.
- SQL assistant: read-only DB role, SELECT only, LIMIT 200, 5s statement timeout.
- Audit-log every admin action and every agent run (no prompt bodies if PII).
- Map controls to OWASP Top 10 (2021), OWASP ASVS L1, OWASP Top 10 for LLM Apps.

## LLM cost controls (runtime)
- Per-module default model = cheapest capable; `max_tokens` cap from MODULE.md.
- Per-user daily token cap on platform key; BYOK bypasses cap but not rate limit.
- Cache identical (module, config, input-hash) results for 10 minutes.
- Record tokens_in, tokens_out, est_cost_usd, latency_ms, status per run.

## Accessibility & performance
- WCAG 2.2 AA, visible focus, keyboard nav, aria-live for streamed output, reduced motion.
- Lighthouse >= 90 perf, >= 95 a11y; p95 page < 500 ms excluding LLM time.

## Definition of Done (every phase)
Tests green; coverage >= 80% on `app/services/`; ruff/mypy/bandit/pip-audit clean;
AC table all PASS; docs updated; CHANGELOG entry; tagged release.

## Out of scope (prototype)
Payments, multi-tenant orgs, vector DB, mobile apps.
