# ADR-004: MODULE.md as the runtime guardrail
**Status:** Accepted · **Date:** 2026-11-24
**Decision:** Each agent is defined by `modules/<id>/MODULE.md`. The front-matter holds metadata and limits; the "System guardrail" section is the system prompt, always placed first. User persona, tone and format are appended as lower-priority preferences, and user input is delimited as data. The registry syncs modules into the DB at startup, while admin-controlled flags (enabled, limits) live in the DB.
**Consequences:** Guardrails are versioned, reviewed in PRs and shown in the admin UI. Adding a module is a file plus a test.
