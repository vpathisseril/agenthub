"""Seed ~30 days of realistic demo activity for the admin analytics dashboard.

Usage: python -m scripts.seed_demo   (safe to re-run; adds demo users once)
"""

from __future__ import annotations

import random
from datetime import timedelta

from sqlalchemy import select

from app.core.db import SessionLocal
from app.core.security import hash_password
from app.llm.base import estimate_cost
from app.main import bootstrap
from app.models import AgentRun, AuditLog, Module, SignupRequest, User, UserModuleAccess, utcnow

NAMES = [
    "Priya Shah",
    "Marcus Lee",
    "Elena Rossi",
    "Daniel Kim",
    "Aisha Bello",
    "Tom Becker",
    "Sofia Alvarez",
    "Ryan O'Neil",
    "Mei Chen",
    "Jordan Price",
    "Fatima Noor",
    "Luca Bianchi",
]
PROVIDERS = {"anthropic": "claude-haiku-5-5", "openai": "gpt-4o-mini", "gemini": "gemini-2.5-flash"}


def main() -> None:
    bootstrap()
    rng = random.Random(7)
    now = utcnow()
    with SessionLocal() as db:
        if db.scalar(select(User).where(User.email.like("%@demo.agenthub.dev"))):
            print("Demo data already present.")
            return
        modules = [m.id for m in db.scalars(select(Module))]
        pw = hash_password("Demo-User-Pass-1")
        users = []
        for i, name in enumerate(NAMES):
            created = now - timedelta(days=rng.randint(1, 29), hours=rng.randint(0, 23))
            if i == 11:
                created = now - timedelta(hours=5)  # one request still inside the SLA window
            manual = i % 3 == 0
            status = "pending" if i in (10, 11) else "active"
            u = User(
                email=f"{name.split()[0].lower()}.{i}@demo.agenthub.dev",
                full_name=name,
                password_hash=pw,
                status=status,
                created_at=created,
                last_login_at=created + timedelta(days=rng.randint(0, 3))
                if status == "active"
                else None,
            )
            db.add(u)
            db.flush()
            decided = (
                created + timedelta(hours=rng.choice([1, 3, 6, 18, 30])) if manual else created
            )
            db.add(
                SignupRequest(
                    user_id=u.id,
                    mode="manual" if (manual or status == "pending") else "auto",
                    status="approved" if status == "active" else "pending",
                    requested_at=created,
                    sla_due_at=created + timedelta(hours=24)
                    if (manual or status == "pending")
                    else None,
                    decided_at=decided if status == "active" else None,
                    decided_by="admin@example.com" if manual else "system:auto",
                )
            )
            if status == "active":
                for m in modules:
                    db.add(UserModuleAccess(user_id=u.id, module_id=m))
                users.append(u)
        weights = {
            "career_coach": 5,
            "sql_assistant": 4,
            "requirements_analyst": 3,
            "status_report": 3,
            "research_summarizer": 2,
        }
        for day in range(30):
            for _ in range(rng.randint(6, 22) + day // 3):
                u = rng.choice(users)
                mod = rng.choices(list(weights), list(weights.values()))[0]
                prov = rng.choices(list(PROVIDERS), [6, 3, 2])[0]
                t_in, t_out = rng.randint(400, 2600), rng.randint(150, 1100)
                status = rng.choices(["ok", "cached", "error"], [90, 7, 3])[0]
                if status == "cached":
                    t_in = t_out = 0
                db.add(
                    AgentRun(
                        user_id=u.id,
                        module_id=mod,
                        provider=prov,
                        model=PROVIDERS[prov],
                        key_source=rng.choices(["platform", "byok"], [85, 15])[0],
                        tokens_in=t_in,
                        tokens_out=t_out,
                        est_cost_usd=estimate_cost(prov, t_in, t_out),
                        latency_ms=rng.randint(5, 30)
                        if status == "cached"
                        else int(rng.lognormvariate(7.4, 0.45)),
                        status=status,
                        error="Provider error 529." if status == "error" else "",
                        created_at=now
                        - timedelta(
                            days=29 - day, hours=rng.randint(0, 23), minutes=rng.randint(0, 59)
                        ),
                    )
                )
        for u in users[:6]:
            db.add(
                AuditLog(
                    actor="admin@example.com",
                    action="signup.approve",
                    target=u.email,
                    created_at=u.created_at + timedelta(hours=2),
                )
            )
        db.commit()
        print(f"Seeded {len(NAMES)} demo users and 30 days of runs.")


if __name__ == "__main__":
    main()
