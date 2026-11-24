"""Owner notifications for the approval workflow (AC-NTF-*)."""

from __future__ import annotations

import smtplib
from datetime import timedelta
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models import SignupRequest, utcnow
from app.services import approval, notify
from app.services.settings_store import set_setting
from tests.conftest import admin_client, csrf, signup


# AC-NTF-1
def test_manual_signup_emails_owner_with_instructions(client: TestClient, db: Session) -> None:
    set_setting(db, "approval_mode", "manual")
    signup(client, email="sam@example.com", name="Sam Doe")
    assert len(notify.sent) == 1
    msg = notify.sent[0]
    body = msg.get_content()
    assert msg["To"] == "owner@example.com"
    assert "Access request from Sam Doe" in msg["Subject"] and "decide by" in msg["Subject"]
    assert "sam@example.com" in body and "Decide by:" in body
    assert "Admin > Users & access" in body and "/admin/users" in body and "Approve" in body


# AC-NTF-2
def test_auto_signup_sends_fyi(client: TestClient) -> None:
    signup(client)
    msg = notify.sent[-1]
    assert "auto-approved" in msg["Subject"] and "suspended" in msg.get_content()


# AC-NTF-3
def test_sla_breach_alert(db: Session) -> None:
    set_setting(db, "approval_mode", "manual")
    user = approval.register(db, "late@example.com", "Late Req", "Str0ng-Password-1")
    req = db.scalar(select(SignupRequest).where(SignupRequest.user_id == user.id))
    assert req is not None
    req.sla_due_at = utcnow() - timedelta(minutes=5)
    db.commit()
    approval.check_sla(db)
    assert "OVERDUE" in notify.sent[-1]["Subject"]


def test_no_owner_email_means_no_send(db: Session) -> None:
    set_setting(db, "notify_email", "")
    set_setting(db, "approval_mode", "manual")
    user = approval.register(db, "x@example.com", "X", "Str0ng-Password-1")
    req = approval.latest_request(db, user)
    assert req is not None and notify.notify_signup(db, req) is False


def test_smtp_backend(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: dict[str, Any] = {}

    class FakeSMTP:
        def __init__(self, host: str, port: int, timeout: int) -> None:
            calls["host"] = (host, port)

        def __enter__(self) -> FakeSMTP:
            return self

        def __exit__(self, *a: object) -> None:
            return None

        def starttls(self, context: object) -> None:
            calls["tls"] = True

        def login(self, user: str, pw: str) -> None:
            calls["login"] = user

        def send_message(self, msg: object) -> None:
            calls["sent"] = msg

    s = get_settings()
    monkeypatch.setattr(s, "email_backend", "smtp")
    monkeypatch.setattr(s, "smtp_user", "bot@example.com")
    monkeypatch.setattr(notify.smtplib, "SMTP", FakeSMTP)
    assert notify.send_email("owner@example.com", "hi", "body") is True
    assert calls["tls"] and calls["login"] == "bot@example.com" and "sent" in calls

    def boom(*a: object, **k: object) -> None:
        raise smtplib.SMTPAuthenticationError(535, b"bad")

    monkeypatch.setattr(notify.smtplib, "SMTP", boom)
    assert notify.send_email("owner@example.com", "hi", "body") is False


# AC-NTF-4
def test_admin_sets_notify_email_and_sends_test(client: TestClient, db: Session) -> None:
    admin_client(client)
    token = csrf(client, "/admin/settings")
    assert 'value="owner@example.com"' in client.get("/admin/settings").text
    r = client.post(
        "/admin/settings",
        data={
            "csrf_token": token,
            "approval_mode": "manual",
            "approval_sla_hours": "24",
            "default_daily_token_cap": "50000",
            "allowed_providers": ["anthropic"],
            "notify_email": "not-an-email",
        },
        follow_redirects=True,
    )
    assert "notification email must be valid" in r.text
    client.post(
        "/admin/settings",
        data={
            "csrf_token": token,
            "approval_mode": "manual",
            "approval_sla_hours": "24",
            "default_daily_token_cap": "50000",
            "allowed_providers": ["anthropic"],
            "notify_email": "boss@example.com",
        },
    )
    r = client.post("/admin/settings/test-email", data={"csrf_token": token}, follow_redirects=True)
    assert "log-only mode" in r.text
    assert notify.sent[-1]["To"] == "boss@example.com"
