"""Post-deploy smoke test. Usage: python -m scripts.smoke https://your-app.replit.app"""

from __future__ import annotations

import sys

import httpx


def main(base: str) -> int:
    base = base.rstrip("/")
    checks = [
        ("/health", 200, '"status":"ok"'),
        ("/", 200, "Request access"),
        ("/login", 200, "Sign in"),
        ("/signup", 200, "Request access"),
        ("/app", 200, "Welcome back"),
        ("/static/css/app.css", 200, "--bg"),
    ]
    failed = 0
    with httpx.Client(follow_redirects=True, timeout=20) as client:
        for path, code, needle in checks:
            r = client.get(base + path)
            ok = r.status_code == code and needle in r.text
            failed += not ok
            print(f"{'PASS' if ok else 'FAIL'}  {path:<22} {r.status_code}")
        csp = client.get(base + "/").headers.get("content-security-policy", "")
        ok = "default-src 'self'" in csp
        failed += not ok
        print(f"{'PASS' if ok else 'FAIL'}  security headers")
    print("ALL PASS" if not failed else f"{failed} FAILED")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1] if len(sys.argv) > 1 else "http://localhost:8000"))
