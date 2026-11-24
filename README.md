# AgentHub

**A governed, multi-model AI agent platform** — approved users configure purpose-built
agents (career, research, data/SQL, status reporting, requirements analysis) while admins
control access, cost, and audit. Built end to end with a gated SDLC and deployed GitHub → Replit.

*By Varghese Pathisseril*

> Status: **Phase 0 — skeleton** (`v0.0`). Live link and screenshots arrive at `v1.0`.

## Features (target)
- Landing page + signup with **auto-approval** or **manual approval within a 24-hour SLA**
- Login, role-based access (user / admin), module-level grants
- **Agent Builder**: provider, model, persona, tone, temperature, max tokens, templates
- **Hybrid LLM keys**: platform key with per-user daily token caps, or bring-your-own key (encrypted)
- **Admin console**: modules, access, settings, reporting & analytics, audit log
- **Guardrails as code**: `CLAUDE.md` (engineering) + `modules/*/MODULE.md` (runtime agent guardrails)

## Starter modules
| Module | Icon | Purpose |
| --- | --- | --- |
| Career Coach | briefcase | Resume ↔ JD match, rewritten bullets, STAR interview prep |
| Research Summarizer | book-open | Executive summary of text or one URL |
| Data / SQL Assistant | database | Plain-English questions → read-only SQL on a telecom sample |
| Status Report Writer | file-text | Notes → RAG executive weekly status |
| Requirements Analyst | list-checks | Raw ask → INVEST stories, Gherkin AC, approach |

## Stack
Python 3.12 · FastAPI · SQLAlchemy/Alembic · Postgres · Jinja2 + HTMX + Alpine.js ·
Tailwind CSS · Lucide · pytest · ruff · mypy · bandit · pip-audit · gitleaks · GitHub Actions · Replit

## Phases (SDLC)
| Phase | Deliverable | Tag |
| --- | --- | --- |
| 0 Setup | Skeleton, guardrails, CI | v0.0 |
| 1 Requirements | `docs/01-requirements.md` | v0.1 |
| 2 Design | `docs/02-design.md`, `docs/04-security.md` | v0.2 |
| 3 Core build | Auth, approval, RBAC, landing | v0.3 |
| 4 Agents & modules | LLM layer, 5 modules, Agent Builder | v0.4 |
| 5 Admin & analytics | Admin console, dashboards, audit | v0.5 |
| 6 Quality & security | Coverage, scans, e2e, a11y | v0.6 |
| 7 Deploy | Live on Replit | v1.0 |

## Run locally
```bash
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
cp .env.example .env
uvicorn app.main:app --reload     # http://localhost:8000/health
pytest && ruff check . && mypy
```

## Standards
OWASP Top 10 (2021) · OWASP ASVS L1 · OWASP Top 10 for LLM Applications · WCAG 2.2 AA ·
12-Factor App · Conventional Commits · SemVer · C4 model · INVEST + Gherkin · NIST AI RMF (framing)
