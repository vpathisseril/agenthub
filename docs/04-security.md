# 04 — Security

## STRIDE threat model
| Threat | Example | Mitigation |
| --- | --- | --- |
| Spoofing | Credential stuffing | argon2id hashing, 10 login attempts per 5 min per IP, generic error message, failed logins audited |
| Tampering | Forged cross-site POST | Per-session CSRF token on every POST (form field or `X-CSRF-Token`), `SameSite=Lax` cookie |
| Repudiation | Admin denies changing access | Append-only `audit_log` for logins, approvals, grants, caps, module and settings changes |
| Information disclosure | API key leak | Fernet encryption at rest; only the last 4 characters displayed; keys never logged; prompt bodies not stored |
| Denial of service | Token burn | Per-user daily caps, `max_tokens` clamped to the module cap, 8k input limit, run rate limit, 10-min cache |
| Elevation of privilege | User reaches /admin, or an admin locks themselves out | Router-level `require_admin`; self-demotion and self-suspension blocked |

## OWASP Top 10 (2021) mapping
| Risk | Control |
| --- | --- |
| A01 Broken access control | RBAC dependencies; per-module grant check on every builder and run request; tests AC-RBAC-1, AC-MOD-2 |
| A02 Cryptographic failures | argon2id; Fernet for BYOK; HSTS and `https_only` cookies in prod |
| A03 Injection | ORM-parameterised queries; SQL agent is SELECT-only behind a validator, an SQLite authorizer, read-only mode and a 5s timeout |
| A04 Insecure design | Threat model, guardrails as code, gated SDLC |
| A05 Security misconfiguration | Strict CSP (`'self'` only, no inline script or style), X-Frame-Options DENY, nosniff, Referrer-Policy, Permissions-Policy, docs disabled; prod refuses to start with the default `SECRET_KEY` |
| A06 Vulnerable components | `pip-audit` in CI; minimal dependencies; no CDN at runtime |
| A07 Auth failures | Password policy (12+ chars, mixed case, digit), session fixation prevented (session cleared at login), 12h session lifetime |
| A08 Integrity failures | CI on protected `main`; gitleaks; pinned major versions |
| A09 Logging failures | Audit log and `agent_runs` telemetry; admin viewer with filters |
| A10 SSRF | URL fetching deliberately not implemented (ADR-005) |

## OWASP Top 10 for LLM Applications
| Risk | Control |
| --- | --- |
| LLM01 Prompt injection | MODULE.md guardrail is always the system prompt; user preferences are explicitly lower priority; input sits inside `<user_input>` and the delimiter is stripped from user text; tests AC-RUN-4 |
| LLM02 Insecure output handling | All model output is HTML-escaped before the Markdown subset renders; never executed. SQL output is validated before it runs |
| LLM04 Model DoS | Caps, `max_tokens` clamp, rate limits, cache |
| LLM06 Sensitive info disclosure | Prompts not logged; keys encrypted; the sample data is synthetic |
| LLM08 Excessive agency | The only tool is read-only SQL on an isolated sample DB; no write tools |
| LLM09 Overreliance | Career and research guardrails forbid fabrication; demo-mode banner when no key is set |
| LLM10 Model theft / cost abuse | Per-user caps and admin-controlled provider allow-list |

## Scan results (Phase 6, v0.6)
| Tool | Result |
| --- | --- |
| ruff (E, F, I, B, UP, S, SIM) | 0 issues |
| mypy --strict (app/) | 0 issues, 28 files |
| bandit -r app | 0 issues (2 reviewed `nosec`: escaped `Markup`, seeded demo RNG) |
| pip-audit -r requirements.txt | No known vulnerabilities |
| pytest | 66 passed, 95% line coverage (services 99%) |
