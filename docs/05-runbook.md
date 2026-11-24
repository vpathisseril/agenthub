# 05 — Runbook: GitHub → Replit

## 1. Push to GitHub
```bash
git remote add origin https://github.com/<you>/agenthub.git
git push -u origin main --tags
```
In GitHub, go to Settings → Branches → add a rule for `main`: require a pull request and require the **CI / quality** check to pass.

## 2. Import into Replit
1. Replit → **Create App → Import from GitHub** → choose `agenthub`. `.replit` is detected automatically.
2. **Database tool → Create a PostgreSQL database.** Replit adds `DATABASE_URL` to Secrets.
3. **Secrets** (padlock icon). Add:

| Secret | Value |
| --- | --- |
| `ENVIRONMENT` | `prod` |
| `SECRET_KEY` | `python -c "import secrets;print(secrets.token_urlsafe(48))"` |
| `FERNET_KEY` | `python -c "from cryptography.fernet import Fernet;print(Fernet.generate_key().decode())"` |
| `ADMIN_EMAIL` / `ADMIN_PASSWORD` | Your admin login (a strong password) |
| `ANTHROPIC_API_KEY` (optional) | Platform key. Leave all keys blank to run in demo mode |
| `OPENAI_API_KEY`, `GEMINI_API_KEY` (optional) | Additional providers |

4. Press **Run**. The run command applies migrations (`alembic upgrade head`) and then starts uvicorn on port 8000. Open the webview and sign in as the admin.
5. Optional: run `python -m scripts.seed_demo` in the Shell to fill the analytics dashboard with 30 days of demo data.

## 3. Deploy
**Deploy → Autoscale** (the build and run commands come from `.replit`). Make sure the deployment has the same Secrets. Then run the smoke test against the live URL:
```bash
python -m scripts.smoke https://<your-app>.replit.app
```

## Approval email notifications
The owner address (`ADMIN_NOTIFY_EMAIL`, or Admin → Settings → *Approval notification email*) gets:
- **Manual mode:** an email for every new request, with the requester's details, the SLA deadline and step-by-step approval instructions linking to `/admin/users`.
- **Auto mode:** an FYI for every auto-approved signup, with how to suspend access.
- **SLA breach:** an "OVERDUE" alert when a pending request passes its deadline.

To deliver real email (default is log-only), add these Secrets and redeploy:

| Secret | Gmail example |
| --- | --- |
| `EMAIL_BACKEND` | `smtp` |
| `SMTP_HOST` / `SMTP_PORT` | `smtp.gmail.com` / `587` |
| `SMTP_USER` | the Gmail address that sends |
| `SMTP_PASSWORD` | a Gmail **App Password** (Google Account → Security → 2-Step Verification → App passwords) |
| `APP_BASE_URL` | your live URL, for links in the email |

Then use **Admin → Settings → Send test email** to confirm delivery.

## Operations
| Task | How |
| --- | --- |
| Update | Merge a PR to `main` → in Replit, pull from the Git pane → Redeploy |
| Roll back | `git checkout v0.N` (or revert) → push → Redeploy; Replit also keeps previous deployments |
| Rotate SECRET_KEY | Update the Secret and redeploy (signs everyone out) |
| Rotate FERNET_KEY | Users must re-enter their BYOK keys (old ciphertext can't be decrypted) |
| Health | `GET /health` returns status, environment and module list |
| Change approval policy | Admin → Settings (no redeploy) |

## Notes
- Rate limiting and the response cache are in-memory, per instance. Keep Autoscale at max 1 instance for the prototype, or move both to Redis.
- Local dev with SQLite creates tables automatically. With Postgres, always use `alembic upgrade head`.
