# 03 — Test Plan & Results

## Strategy
| Layer | Tooling | Scope |
| --- | --- | --- |
| Unit | pytest | Security helpers, Markdown sanitizer, module registry, SQL sandbox, provider adapters (mocked HTTP) |
| Service | pytest + SQLite | Approval workflow and SLA, agent pipeline (caps, BYOK, cache, errors, injection), analytics |
| API / acceptance | FastAPI TestClient | Every AC in 01-requirements, end to end through HTTP, CSRF and sessions |
| UI | Playwright screenshots (`scripts/shoot.py`) | Landing, auth, dashboard, builder, admin pages in desktop, mobile and light themes; console-error check |
| Static | ruff, mypy --strict, bandit, pip-audit, gitleaks | Every push (CI) |

The LLM is replaced by `FakeProvider` (`LLM_FAKE_MODE=true`), so tests are deterministic, offline and cost nothing.

## Results (v0.6)
- **66 tests passed, 0 failed**; line coverage **95%** overall, **99%** on `app/services/` (gate: 80%).
- AC table: every AC-* scenario in 01-requirements has a passing test (see the traceability matrix).
- UI review: no console errors on any page; WCAG checks: visible focus ring, skip link, labelled inputs, `aria-live` on output, `prefers-reduced-motion` honoured, text contrast ≥ 4.5:1 on the dark theme (#e5e7eb on #111827 ≈ 14:1; #a7b0c0 on #111827 ≈ 8:1).

## Run locally
```bash
pip install -r requirements.txt pytest pytest-cov ruff mypy bandit pip-audit types-PyYAML
pytest --cov=app && ruff check . && mypy && bandit -q -r app -c pyproject.toml
```
