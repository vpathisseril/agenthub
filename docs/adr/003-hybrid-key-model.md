# ADR-003: Hybrid LLM key model
**Status:** Accepted · **Date:** 2026-11-24
**Decision:** By default runs use a platform key, metered by a per-user daily token cap. Users can add their own key for any provider (Fernet-encrypted). BYOK runs skip the cap but not the rate limit. With no key at all, a deterministic demo model answers, so the product can always be demoed.
**Consequences:** Cost stays predictable, and power users aren't blocked. Pricing is estimated from a list-price table (`app/llm/base.py`) that must be kept current.
