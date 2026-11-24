"""Email notifications to the platform owner (approval workflow).

Backends (EMAIL_BACKEND):
- "log"  (default): writes the message to the app log, so nothing is lost when email
  isn't configured.
- "smtp": sends via any SMTP relay (Gmail app password, SendGrid, Resend, ...).
Sending never raises: a failed email must not block a signup.
"""

from __future__ import annotations

import logging
import re
import smtplib
import ssl
from email.message import EmailMessage

from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models import SignupRequest
from app.services.settings_store import get_setting

log = logging.getLogger("agenthub.notify")
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
sent: list[EmailMessage] = []  # last messages (inspected by tests and the admin UI)


def owner_email(db: Session) -> str:
    return get_setting(db, "notify_email").strip()


def send_email(to: str, subject: str, body: str) -> bool:
    s = get_settings()
    msg = EmailMessage()
    msg["From"] = s.smtp_from or s.smtp_user or "AgentHub <no-reply@agenthub.app>"
    msg["To"] = to
    msg["Subject"] = subject
    msg.set_content(body)
    sent.append(msg)
    del sent[:-20]
    if s.email_backend != "smtp":
        log.info("EMAIL (log backend) to=%s subject=%s\n%s", to, subject, body)
        return True
    try:
        with smtplib.SMTP(s.smtp_host, s.smtp_port, timeout=15) as smtp:
            smtp.starttls(context=ssl.create_default_context())
            if s.smtp_user:
                smtp.login(s.smtp_user, s.smtp_password)
            smtp.send_message(msg)
        log.info("Email sent to %s: %s", to, subject)
        return True
    except (smtplib.SMTPException, OSError) as exc:
        log.warning("Email to %s failed: %s", to, exc)
        return False


def _base(base_url: str | None) -> str:
    return (base_url or get_settings().app_base_url or "").rstrip("/")


def _instructions(base: str) -> str:
    admin = f"{base}/admin/users" if base else "/admin/users"
    login = f"{base}/login" if base else "/login"
    return (
        "How to approve or reject:\n"
        f"  1. Sign in as the admin: {login}\n"
        f"  2. Open Admin > Users & access: {admin}\n"
        "  3. In the Approval queue, find the request and click Approve (or Reject).\n"
        "  4. Approved users can sign in immediately and get the default modules.\n"
        "     Adjust their modules or daily token cap with 'Edit access' in the same list.\n"
    )


def notify_signup(db: Session, req: SignupRequest, base_url: str | None = None) -> bool:
    to = owner_email(db)
    if not EMAIL_RE.match(to):
        return False
    u, base = req.user, _base(base_url)
    details = (
        f"Name:      {u.full_name}\nEmail:     {u.email}\n"
        f"Requested: {req.requested_at:%b %d, %Y %H:%M} UTC\n"
        f"Reason:    {req.reason or '(none given)'}\n"
    )
    if req.status == "pending":
        deadline = f"{req.sla_due_at:%b %d, %Y %H:%M} UTC" if req.sla_due_at else "n/a"
        subject = f"[AgentHub] Access request from {u.full_name} — decide by {deadline}"
        body = (
            "A new AgentHub access request is waiting for your decision.\n\n"
            f"{details}Decide by: {deadline} (approval SLA)\n\n{_instructions(base)}"
        )
    else:
        subject = f"[AgentHub] New user auto-approved: {u.full_name}"
        body = (
            "A new user signed up and was approved automatically (approval mode: auto).\n\n"
            f"{details}\nNo action needed. To remove access, open Admin > Users & access, "
            "click 'Edit access' on the user and set Status to suspended.\n"
            "To review every signup first, switch Admin > Settings > Approval mode to "
            f"'Manual review with SLA'.\n\n{_instructions(base)}"
        )
    return send_email(to, subject, body)


def notify_sla_breach(db: Session, req: SignupRequest, auto_approved: bool) -> bool:
    to = owner_email(db)
    if not EMAIL_RE.match(to):
        return False
    u = req.user
    status = (
        "It was auto-approved (SLA breach policy)." if auto_approved else "It is still pending."
    )
    body = (
        f"The access request from {u.full_name} <{u.email}> missed its approval SLA "
        f"({req.sla_due_at:%b %d, %Y %H:%M} UTC). {status}\n\n{_instructions(_base(None))}"
    )
    return send_email(to, f"[AgentHub] OVERDUE access request: {u.full_name}", body)
