# ADR-001: HTMX + server-rendered templates instead of an SPA
**Status:** Accepted · **Date:** 2026-11-24
**Context:** This is a prototype built by one person. It needs fast pages, a strict CSP and a single deployable.
**Decision:** Jinja2 templates plus HTMX for partial updates (agent runs). A small vanilla JS file handles the theme toggle, copy and range labels.
**Consequences:** No Node build in prod, a tiny JS payload and strict CSP compliance. Very rich client state would need a rethink.
