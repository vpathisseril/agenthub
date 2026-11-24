"""HTTP-level acceptance tests mapped to docs/01-requirements.md AC IDs."""

from __future__ import annotations

import re

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import ApiKey, AuditLog, Module, SignupRequest, User
from app.services.settings_store import set_setting
from tests.conftest import STRONG_PW, admin_client, csrf, signup


# AC-LND-1
def test_landing_page_public(client: TestClient) -> None:
    r = client.get("/")
    assert r.status_code == 200
    assert "Request access" in r.text and "Career Coach" in r.text


# AC-SEC-1
def test_security_headers(client: TestClient) -> None:
    h = client.get("/").headers
    assert "default-src 'self'" in h["content-security-policy"]
    assert h["x-frame-options"] == "DENY" and h["x-content-type-options"] == "nosniff"


# AC-SGN-1
def test_signup_auto_approve_signs_in(client: TestClient) -> None:
    r = signup(client)
    assert r.status_code == 303 and r.headers["location"] == "/app"
    assert "Good to see you, Pat" in client.get("/app").text


# AC-SGN-2
def test_signup_weak_password_rejected(client: TestClient) -> None:
    r = signup(client, password="weak")
    assert r.status_code == 422 and "12 characters" in r.text


# AC-SGN-3
def test_signup_duplicate_email(client: TestClient) -> None:
    signup(client)
    client.post("/logout", data={"csrf_token": csrf(client, "/app")})
    r = signup(client, email="PAT@example.com")
    assert r.status_code == 409


# AC-APR-1 / AC-APR-2
def test_manual_mode_pending_then_admin_approves(client: TestClient, db: Session) -> None:
    set_setting(db, "approval_mode", "manual")
    r = signup(client)
    assert r.headers["location"] == "/pending"
    page = client.get("/pending").text
    assert "pending review" in page and "UTC" in page
    # pending user cannot sign in
    token = csrf(client)
    r = client.post(
        "/login",
        data={"email": "pat@example.com", "password": STRONG_PW, "csrf_token": token},
        follow_redirects=False,
    )
    assert r.headers["location"] == "/pending"
    # admin approves
    admin_client(client)
    req = db.scalar(select(SignupRequest))
    assert req is not None
    assert "pat@example.com" in client.get("/admin/users").text
    r = client.post(
        f"/admin/requests/{req.id}/approve",
        data={"csrf_token": csrf(client, "/admin/users")},
        follow_redirects=False,
    )
    assert r.status_code == 303
    db.expire_all()
    assert db.scalar(select(User.status).where(User.email == "pat@example.com")) == "active"
    assert db.scalar(select(AuditLog).where(AuditLog.action == "signup.approve")) is not None


# AC-AUTH-1
def test_login_wrong_password(client: TestClient) -> None:
    token = csrf(client)
    r = client.post(
        "/login", data={"email": "admin@example.com", "password": "nope", "csrf_token": token}
    )
    assert r.status_code == 401 and "incorrect" in r.text


# AC-AUTH-2
def test_csrf_required(client: TestClient) -> None:
    r = client.post("/login", data={"email": "admin@example.com", "password": "x"})
    assert r.status_code == 403


# AC-AUTH-3
def test_login_rate_limited(client: TestClient) -> None:
    token = csrf(client)
    codes = [
        client.post(
            "/login", data={"email": "a@b.co", "password": "x", "csrf_token": token}
        ).status_code
        for _ in range(11)
    ]
    assert codes[-1] == 429


# AC-AUTH-4
def test_open_redirect_blocked(client: TestClient) -> None:
    token = csrf(client)
    r = client.post(
        "/login",
        data={
            "email": "admin@example.com",
            "password": "Admin-Pass-2026",
            "csrf_token": token,
            "next": "//evil.example",
        },
        follow_redirects=False,
    )
    assert r.headers["location"] == "/app"


# AC-RBAC-1
def test_anonymous_redirected_and_user_blocked_from_admin(client: TestClient) -> None:
    r = client.get("/app", follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"].startswith("/login")
    signup(client)
    assert client.get("/admin").status_code == 403
    assert client.get("/admin/users").status_code == 403


# AC-MOD-1 / AC-RUN-1
def test_user_configures_and_runs_agent(client: TestClient) -> None:
    signup(client)
    page = client.get("/app/modules/requirements_analyst").text
    cfg_id = re.search(r'name="config_id" value="(\d+)"', page)
    assert cfg_id
    token = csrf(client, "/app")
    r = client.post(
        "/app/modules/requirements_analyst/config",
        data={
            "csrf_token": token,
            "config_id": cfg_id.group(1),
            "name": "Exec BA",
            "provider": "openai",
            "model": "",
            "persona": "Senior BA",
            "tone": "executive",
            "output_format": "markdown",
            "temperature": "0.3",
            "max_tokens": "900",
        },
        follow_redirects=True,
    )
    assert "Saved agent" in r.text and "Exec BA" in r.text
    r = client.post(
        "/app/modules/requirements_analyst/run",
        data={"config_id": cfg_id.group(1), "user_input": "Self-serve churn dashboard"},
        headers={"X-CSRF-Token": token, "HX-Request": "true"},
    )
    assert r.status_code == 200 and "Gherkin" in r.text and "tokens" in r.text


# AC-MOD-2
def test_module_not_granted_is_forbidden(client: TestClient, db: Session) -> None:
    signup(client)
    module = db.get(Module, "sql_assistant")
    assert module is not None
    module.enabled = False
    db.commit()
    assert client.get("/app/modules/sql_assistant").status_code == 403
    assert "Data / SQL Assistant" not in client.get("/app").text


# AC-KEY-1
def test_byok_saved_encrypted(client: TestClient, db: Session) -> None:
    signup(client)
    token = csrf(client, "/app/settings")
    r = client.post(
        "/app/settings/keys",
        data={"csrf_token": token, "provider": "gemini", "api_key": "AIza-secret-9876"},
        follow_redirects=True,
    )
    assert "…9876" in r.text and "AIza-secret" not in r.text
    row = db.scalar(select(ApiKey))
    assert row is not None and "AIza" not in row.encrypted_key
    r = client.post(
        "/app/settings/keys/gemini/delete", data={"csrf_token": token}, follow_redirects=True
    )
    assert "Removed" in r.text


# AC-ADM-1
def test_admin_updates_user_access(client: TestClient, db: Session) -> None:
    signup(client)
    client.post("/logout", data={"csrf_token": csrf(client, "/app")})
    admin_client(client)
    uid = db.scalar(select(User.id).where(User.email == "pat@example.com"))
    token = csrf(client, "/admin/users")
    r = client.post(
        f"/admin/users/{uid}",
        data={
            "csrf_token": token,
            "status": "active",
            "role": "user",
            "daily_token_cap": "1234",
            "modules": ["career_coach"],
        },
        follow_redirects=True,
    )
    assert "cap 50000-&gt;1234" in r.text or "Updated" in r.text
    db.expire_all()
    user = db.get(User, uid)
    assert user is not None and user.daily_token_cap == 1234
    assert [g.module_id for g in user.grants] == ["career_coach"]


# AC-ADM-2
def test_admin_cannot_lock_self_out(client: TestClient, db: Session) -> None:
    admin_client(client)
    uid = db.scalar(select(User.id).where(User.email == "admin@example.com"))
    r = client.post(
        f"/admin/users/{uid}",
        data={"csrf_token": csrf(client, "/admin/users"), "status": "suspended", "role": "admin"},
        follow_redirects=True,
    )
    assert "cannot suspend" in r.text


# AC-ADM-3
def test_admin_module_and_settings(client: TestClient, db: Session) -> None:
    admin_client(client)
    token = csrf(client, "/admin/modules")
    client.post(
        "/admin/modules/status_report",
        data={
            "csrf_token": token,
            "max_tokens": "600",
            "temperature": "0.2",
            "default_provider": "gemini",
        },
    )
    db.expire_all()
    module = db.get(Module, "status_report")
    assert module is not None and not module.enabled and module.max_tokens == 600
    r = client.post(
        "/admin/settings",
        data={
            "csrf_token": token,
            "approval_mode": "manual",
            "approval_sla_hours": "24",
            "default_daily_token_cap": "9000",
            "allowed_providers": ["anthropic"],
        },
        follow_redirects=True,
    )
    assert "Settings saved" in r.text
    assert "status_report" in client.get("/admin/audit").text


# AC-ADM-RPT-1
def test_admin_analytics_and_export(client: TestClient) -> None:
    admin_client(client)
    r = client.get("/admin?days=7")
    assert r.status_code == 200 and 'id="chart-data"' in r.text
    csv = client.get("/admin/analytics.csv?days=7")
    assert csv.headers["content-type"].startswith("text/csv")
    assert csv.text.startswith("created_at,user,module")


def test_unknown_page_404(client: TestClient) -> None:
    assert client.get("/does-not-exist").status_code == 404
