# ADR-002: Postgres on Replit, SQLite for tests
**Status:** Accepted · **Date:** 2026-11-24
**Decision:** SQLAlchemy 2 ORM with Alembic migrations against Replit-managed Postgres (psycopg 3). SQLite is used for local dev and tests.
**Consequences:** The same models run on both. The initial migration has been verified on Postgres 16 and SQLite. The schema avoids engine-specific features.
