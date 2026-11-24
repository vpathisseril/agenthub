# 01 — Requirements & Acceptance Criteria

**Product:** AgentHub, a governed, multi-model AI agent platform (prototype).
**Goal:** approved users run purpose-built AI agents. Admins control access, cost and audit. The app is deployed GitHub → Replit.

## Personas
| Persona | Need |
| --- | --- |
| Visitor | Understand the product quickly and request access |
| Pending user | Know the request status and when it will be decided |
| User | Configure and run agents they are granted, and see cost and usage |
| Admin | Approve users, grant modules, set limits, see usage and cost, audit every action |

## User stories (INVEST, MoSCoW)
| ID | Epic | Story | Priority |
| --- | --- | --- | --- |
| US-LND-1 | Landing | As a visitor, I want a clear landing page so that I understand the value and can request access | Must |
| US-SGN-1 | Signup | As a visitor, I want to sign up with name, email and password so that I can request access | Must |
| US-APR-1 | Approval | As an admin, I want auto or manual approval so that I can match the access policy to risk | Must |
| US-APR-2 | Approval | As a pending user, I want to see the decision deadline (24h SLA) so that I know what to expect | Must |
| US-APR-3 | Approval | As an admin, I want overdue requests flagged (optionally auto-approved) so that the SLA is never silently missed | Should |
| US-AUTH-1 | Auth | As a user, I want secure sign-in and sign-out so that my account is protected | Must |
| US-MOD-1 | Module access | As a user, I want to see only the modules granted to me so that the UI matches my entitlements | Must |
| US-CFG-1 | Agent config | As a user, I want to set provider, model, persona, tone, format, temperature and max tokens, and save presets, so that agents fit how I work | Must |
| US-RUN-1 | Agent run | As a user, I want to run an agent and see the result with tokens, cost and latency so that I understand value and spend | Must |
| US-KEY-1 | BYOK | As a user, I want to add my own API key (encrypted) so that I can go beyond the platform cap | Should |
| US-ADM-1 | Admin access | As an admin, I want to change status, role, module grants and token caps per user | Must |
| US-ADM-2 | Admin modules | As an admin, I want to enable or disable modules and set token, temperature and provider defaults | Must |
| US-ADM-3 | Settings | As an admin, I want to set the approval mode, SLA, default cap and allowed providers | Must |
| US-RPT-1 | Reporting | As an admin, I want KPIs and charts (signups, SLA, DAU/WAU, runs, tokens, cost, errors, p95) with CSV export | Must |
| US-AUD-1 | Audit | As an admin, I want an audit log of sign-ins, approvals, access changes and settings | Must |

## Acceptance criteria (Gherkin) → tests
```gherkin
Feature: Signup and approval
  Scenario: AC-SGN-1 Auto-approve signs the user in
    Given approval mode is "auto"
    When a visitor signs up with a valid name, email and strong password
    Then the account is active, default modules are granted, and the user lands on /app

  Scenario: AC-SGN-2 Weak password rejected
    When a visitor signs up with "weak"
    Then the response is 422 and explains the password policy

  Scenario: AC-SGN-3 Duplicate email
    Given "pat@example.com" exists
    When someone signs up with "PAT@example.com"
    Then the response is 409

  Scenario: AC-APR-1 Manual mode sets a 24h SLA
    Given approval mode is "manual"
    When a visitor signs up
    Then the request is pending with sla_due_at = requested_at + 24h
    And the pending page shows the decision deadline

  Scenario: AC-APR-2 Pending user cannot sign in; admin approves
    Given a pending request
    When the user tries to sign in
    Then they are sent to /pending
    When an admin approves the request
    Then the user is active and an audit entry "signup.approve" exists

  Scenario: AC-APR-3 SLA breach
    Given a pending request past its SLA
    When the SLA check runs
    Then the request is flagged as breached, and auto-approved only if that setting is on

Feature: Security
  Scenario: AC-AUTH-1 Wrong password → 401 with a generic message
  Scenario: AC-AUTH-2 Any POST without a valid CSRF token → 403
  Scenario: AC-AUTH-3 More than 10 login attempts in 5 minutes from one IP → 429
  Scenario: AC-AUTH-4 next=//evil.example after login redirects to /app (no open redirect)
  Scenario: AC-RBAC-1 Anonymous user → redirected to /login; non-admin on /admin → 403
  Scenario: AC-SEC-1 Every response carries CSP, X-Frame-Options DENY and nosniff

Feature: Agents
  Scenario: AC-MOD-1 Configure and run
    Given an active user with Requirements Analyst access
    When they save a preset and run it with input
    Then the output shows stories and Gherkin, plus tokens, cost and latency

  Scenario: AC-MOD-2 Disabled or ungranted module
    Then the builder returns 403 and the module is hidden from the dashboard

  Scenario: AC-RUN-2 Daily cap
    Given the user has used their platform token cap today
    When they run an agent without BYOK
    Then the run is blocked with a clear message and recorded as "blocked"

  Scenario: AC-RUN-3 Cache
    When the same input runs twice within 10 minutes
    Then the second run is "cached" and costs 0 tokens

  Scenario: AC-RUN-4 Prompt-injection and SQL safety
    Given input containing "</user_input>" or a model reply with "DELETE FROM"
    Then the delimiter is stripped and no non-SELECT SQL is executed

  Scenario: AC-KEY-1 BYOK stored encrypted, only the last 4 characters shown

Feature: Admin
  Scenario: AC-ADM-1 Update status, role, cap and grants; changes audited
  Scenario: AC-ADM-2 An admin cannot suspend or demote themselves
  Scenario: AC-ADM-3 Module disable and limits; settings change; audit visible
  Scenario: AC-ADM-RPT-1 Dashboard renders for 7/30/90 days; CSV export works
```

## Non-functional requirements
| Area | Requirement | How it's verified |
| --- | --- | --- |
| Security | OWASP Top 10, ASVS L1, OWASP LLM Top 10 controls (see 04-security) | Tests + bandit + pip-audit + gitleaks |
| Accessibility | WCAG 2.2 AA: contrast, focus, keyboard, aria-live output, reduced motion | Manual + axe checklist |
| Performance | p95 page < 500 ms, excluding LLM time; CSS < 50 KB; no blocking JS | Local timing; static assets self-hosted |
| Availability | Single Replit Autoscale deployment; `/health` endpoint | Smoke test |
| Cost | Cheapest capable model per module; per-user daily caps; 10-min cache. Target < $25/month LLM spend at prototype scale | Analytics cost KPI |

## Traceability matrix
| Story | Component | Tests |
| --- | --- | --- |
| US-LND-1 | `api/public.py`, `landing.html` | test_landing_page_public |
| US-SGN-1 | `api/auth.py`, `services/approval.py` | test_signup_* |
| US-APR-1..3 | `services/approval.py`, `admin/users.html` | test_manual_mode_*, test_sla_breach_flagged, test_auto_approval_* |
| US-AUTH-1 | `api/auth.py`, `core/deps.py`, `core/ratelimit.py` | test_login_*, test_csrf_required, test_open_redirect_blocked |
| US-MOD-1 | `services/agents.user_can_use` | test_module_not_granted_is_forbidden |
| US-CFG-1, US-RUN-1 | `api/user.py`, `services/agents.py` | test_user_configures_and_runs_agent, test_run_records_tokens_and_cache |
| US-KEY-1 | `api/user.py`, `core/security.py` | test_byok_saved_encrypted, test_byok_bypasses_cap |
| US-ADM-1..3 | `api/admin.py` | test_admin_* |
| US-RPT-1 | `services/analytics.py`, `admin.js` | test_dashboard_aggregates, test_admin_analytics_and_export |
| US-AUD-1 | `services/audit.py` | test_manual_mode_* (audit), test_admin_module_and_settings |
