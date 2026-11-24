"""Sample telecom dataset for the Data/SQL Assistant + a locked-down query runner.

The dataset lives in its own SQLite file, opened read-only, with an authorizer
that allows only SELECT/READ. The app database is never reachable from here.
"""

from __future__ import annotations

import random
import re
import sqlite3
import time
from datetime import date, timedelta
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parents[2] / "data"
SAMPLE_DB = DATA_DIR / "telecom_sample.db"
MAX_ROWS = 200
TIMEOUT_SECONDS = 5.0

SCHEMA = """
CREATE TABLE customers (id INTEGER PRIMARY KEY, name TEXT, state TEXT, segment TEXT,
  signup_date TEXT);
CREATE TABLE plans (id INTEGER PRIMARY KEY, name TEXT, monthly_price REAL, data_gb INTEGER);
CREATE TABLE subscriptions (id INTEGER PRIMARY KEY, customer_id INTEGER, plan_id INTEGER,
  status TEXT, start_date TEXT);
CREATE TABLE devices (id INTEGER PRIMARY KEY, customer_id INTEGER, make TEXT, model TEXT,
  activated_on TEXT);
CREATE TABLE tickets (id INTEGER PRIMARY KEY, customer_id INTEGER, category TEXT,
  priority TEXT, opened_at TEXT, resolved_at TEXT, csat INTEGER);
"""

SCHEMA_SUMMARY = (
    "customers(id, name, state, segment, signup_date); "
    "plans(id, name, monthly_price, data_gb); "
    "subscriptions(id, customer_id, plan_id, status, start_date); "
    "devices(id, customer_id, make, model, activated_on); "
    "tickets(id, customer_id, category, priority, opened_at, resolved_at, csat)"
)


class QueryRejected(ValueError):
    pass


def build_sample_db(path: Path = SAMPLE_DB) -> Path:
    if path.exists():
        return path
    path.parent.mkdir(parents=True, exist_ok=True)
    rng = random.Random(42)  # noqa: S311  # nosec B311 - synthetic demo data
    con = sqlite3.connect(path)
    con.executescript(SCHEMA)
    states = ["PA", "NJ", "NY", "CA", "TX", "FL", "IL", "GA", "CO", "WA"]
    segments = ["Consumer", "Small Business", "Enterprise"]
    plans = [
        ("Essentials 5GB", 35.0, 5),
        ("Unlimited", 65.0, 999),
        ("Unlimited Plus", 85.0, 999),
        ("Business Pro", 95.0, 999),
        ("By the Gig", 20.0, 1),
    ]
    con.executemany("INSERT INTO plans(name, monthly_price, data_gb) VALUES (?,?,?)", plans)
    makes = {
        "Apple": ["iPhone 16", "iPhone 17"],
        "Samsung": ["Galaxy S25", "Galaxy A56"],
        "Google": ["Pixel 10"],
        "Motorola": ["moto g"],
    }
    cats = ["Billing", "Network", "Device", "Activation", "Porting"]
    start = date(2024, 1, 1)
    for cid in range(1, 501):
        signup = start + timedelta(days=rng.randint(0, 680))
        con.execute(
            "INSERT INTO customers(name, state, segment, signup_date) VALUES (?,?,?,?)",
            (
                f"Customer {cid:04d}",
                rng.choice(states),
                rng.choices(segments, [70, 22, 8])[0],
                signup.isoformat(),
            ),
        )
        con.execute(
            "INSERT INTO subscriptions(customer_id, plan_id, status, start_date) VALUES (?,?,?,?)",
            (
                cid,
                rng.randint(1, 5),
                rng.choices(["active", "cancelled"], [85, 15])[0],
                signup.isoformat(),
            ),
        )
        make = rng.choice(list(makes))
        con.execute(
            "INSERT INTO devices(customer_id, make, model, activated_on) VALUES (?,?,?,?)",
            (cid, make, rng.choice(makes[make]), signup.isoformat()),
        )
        for _ in range(rng.choices([0, 1, 2, 3], [45, 30, 15, 10])[0]):
            opened = signup + timedelta(days=rng.randint(1, 200))
            con.execute(
                "INSERT INTO tickets(customer_id, category, priority, opened_at, resolved_at, csat)"
                " VALUES (?,?,?,?,?,?)",
                (
                    cid,
                    rng.choice(cats),
                    rng.choice(["Low", "Medium", "High"]),
                    opened.isoformat(),
                    (opened + timedelta(days=rng.randint(0, 9))).isoformat(),
                    rng.randint(1, 5),
                ),
            )
    con.commit()
    con.close()
    return path


_ALLOWED_ACTIONS = {sqlite3.SQLITE_SELECT, sqlite3.SQLITE_READ, sqlite3.SQLITE_FUNCTION}


def _authorizer(action: int, *_: object) -> int:
    return sqlite3.SQLITE_OK if action in _ALLOWED_ACTIONS else sqlite3.SQLITE_DENY


def validate_sql(sql: str) -> str:
    cleaned = re.sub(r"--[^\n]*", "", sql).strip().rstrip(";").strip()
    if not cleaned:
        raise QueryRejected("No SQL found.")
    if ";" in cleaned:
        raise QueryRejected("Only a single statement is allowed.")
    if not re.match(r"^(select|with)\b", cleaned, re.I):
        raise QueryRejected("Only SELECT queries are allowed.")
    if re.search(
        r"\b(attach|pragma|insert|update|delete|drop|alter|create|replace)\b", cleaned, re.I
    ):
        raise QueryRejected("Query contains a disallowed keyword.")
    return cleaned


def run_readonly(sql: str, path: Path = SAMPLE_DB) -> tuple[list[str], list[tuple[object, ...]]]:
    cleaned = validate_sql(sql)
    build_sample_db(path)
    con = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    try:
        deadline = time.monotonic() + TIMEOUT_SECONDS
        con.set_progress_handler(lambda: int(time.monotonic() > deadline), 10_000)
        con.set_authorizer(_authorizer)
        try:
            cur = con.execute(cleaned)
            rows = cur.fetchmany(MAX_ROWS)
        except sqlite3.DatabaseError as exc:
            raise QueryRejected(f"Query failed: {exc}") from exc
        cols = [d[0] for d in cur.description or []]
        return cols, rows
    finally:
        con.close()
