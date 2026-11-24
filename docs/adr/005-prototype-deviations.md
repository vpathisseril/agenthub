# ADR-005: Deviations from the original build plan
**Status:** Accepted · **Date:** 2026-11-24
| Planned | Built | Why |
| --- | --- | --- |
| Tailwind CSS (CLI build) | Hand-written token-based CSS (`app/static/css/app.css`, ~20 KB) | No build step on Replit; tokens map 1:1 to docs/design-tokens.md |
| Alpine.js | ~60 lines of vanilla JS | Alpine's standard build needs `unsafe-eval`, which breaks the strict CSP |
| Research Summarizer URL fetch | Pasted text only | Avoids SSRF risk (OWASP A10); can return later with an allow-list and a fetch proxy |
| SSE streaming output | HTMX request with a loading state | Simpler and testable; runs are under 10s with capped tokens |
| SQL agent on a Postgres read-only role | Separate read-only SQLite sandbox with an authorizer | Works identically on any host and fully isolates the app DB |
| APScheduler for the SLA | Hourly asyncio task, plus a check on every admin page load | No extra dependency; one instance |
