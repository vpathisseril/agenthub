"""Reporting & analytics aggregations for the admin dashboard."""

from __future__ import annotations

import statistics
from collections import Counter, defaultdict
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import AgentRun, SignupRequest, User, utcnow


def _p95(values: list[int]) -> int:
    if not values:
        return 0
    values = sorted(values)
    idx = max(0, int(round(0.95 * len(values))) - 1)
    return values[idx]


def dashboard(db: Session, days: int = 30) -> dict[str, Any]:
    now = utcnow()
    since = now - timedelta(days=days)
    day_keys = [(since + timedelta(days=i + 1)).date().isoformat() for i in range(days)]

    runs = db.scalars(select(AgentRun).where(AgentRun.created_at >= since)).all()
    reqs = db.scalars(select(SignupRequest).where(SignupRequest.requested_at >= since)).all()
    users = {u.id: u for u in db.scalars(select(User)).all()}

    real = [r for r in runs if r.status in ("ok", "cached", "error")]
    errors = sum(1 for r in real if r.status == "error")
    tokens = sum(r.tokens_in + r.tokens_out for r in runs)
    cost = sum(r.est_cost_usd for r in runs)

    decided = [r for r in reqs if r.status == "approved" and r.decided_at and r.mode == "manual"]
    approve_hours = [
        (r.decided_at - r.requested_at).total_seconds() / 3600 for r in decided if r.decided_at
    ]
    within = [r for r in decided if r.sla_due_at and r.decided_at and r.decided_at <= r.sla_due_at]

    dau_cut, wau_cut = now - timedelta(days=1), now - timedelta(days=7)
    dau = len({r.user_id for r in runs if r.created_at >= dau_cut})
    wau = len({r.user_id for r in runs if r.created_at >= wau_cut})

    modules = sorted({r.module_id for r in runs})
    by_mod_day: dict[str, Counter[str]] = defaultdict(Counter)
    for r in runs:
        by_mod_day[r.module_id][r.created_at.date().isoformat()] += 1
    signups_by_day = Counter(r.requested_at.date().isoformat() for r in reqs)

    cost_by_provider: dict[str, float] = defaultdict(float)
    tok_by_user: Counter[int] = Counter()
    runs_by_module: Counter[str] = Counter()
    for r in runs:
        cost_by_provider[r.provider] += r.est_cost_usd
        tok_by_user[r.user_id] += r.tokens_in + r.tokens_out
        runs_by_module[r.module_id] += 1

    pending_all = db.scalars(select(SignupRequest).where(SignupRequest.status == "pending")).all()

    return {
        "days": days,
        "kpis": {
            "signups": len(reqs),
            "pending": len(pending_all),
            "overdue": sum(1 for r in pending_all if r.sla_due_at and r.sla_due_at < now),
            "median_approval_h": round(statistics.median(approve_hours), 1)
            if approve_hours
            else None,
            "pct_within_sla": round(100 * len(within) / len(decided)) if decided else None,
            "dau": dau,
            "wau": wau,
            "runs": len(runs),
            "tokens": tokens,
            "cost": round(cost, 4),
            "error_rate": round(100 * errors / len(real), 1) if real else 0.0,
            "p95_ms": _p95([r.latency_ms for r in real if r.status != "cached"]),
        },
        "labels": day_keys,
        "runs_series": {m: [by_mod_day[m].get(d, 0) for d in day_keys] for m in modules},
        "signups_series": [signups_by_day.get(d, 0) for d in day_keys],
        "cost_by_provider": {k: round(v, 4) for k, v in sorted(cost_by_provider.items())},
        "runs_by_module": dict(runs_by_module.most_common()),
        "top_users": [
            {"email": users[uid].email if uid in users else f"#{uid}", "tokens": t}
            for uid, t in tok_by_user.most_common(8)
        ],
    }


def runs_csv_rows(db: Session, days: int = 30) -> list[list[str]]:
    since = utcnow() - timedelta(days=days)
    users = {u.id: u.email for u in db.scalars(select(User)).all()}
    rows = [
        [
            "created_at",
            "user",
            "module",
            "provider",
            "model",
            "key_source",
            "tokens_in",
            "tokens_out",
            "est_cost_usd",
            "latency_ms",
            "status",
        ]
    ]
    for r in db.scalars(
        select(AgentRun).where(AgentRun.created_at >= since).order_by(AgentRun.created_at)
    ):
        rows.append(
            [
                r.created_at.isoformat(timespec="seconds"),
                users.get(r.user_id, ""),
                r.module_id,
                r.provider,
                r.model,
                r.key_source,
                str(r.tokens_in),
                str(r.tokens_out),
                f"{r.est_cost_usd:.6f}",
                str(r.latency_ms),
                r.status,
            ]
        )
    return rows


def as_of() -> datetime:
    return utcnow()
