"""Unit tests: security helpers, markdown sanitizer, module registry, SQL sandbox."""

from __future__ import annotations

import pytest

from app.core.security import (
    csrf_matches,
    decrypt_secret,
    encrypt_secret,
    hash_password,
    password_problems,
    verify_password,
)
from app.services import sample_data
from app.services.markdown_lite import render_markdown
from app.services.modules_registry import load_specs, parse_module


def test_password_hash_roundtrip() -> None:
    h = hash_password("Correct-Horse-9")
    assert h.startswith("$argon2")
    assert verify_password(h, "Correct-Horse-9")
    assert not verify_password(h, "wrong")
    assert not verify_password("not-a-hash", "x")


@pytest.mark.parametrize(
    ("pw", "ok"),
    [
        ("short1A", False),
        ("alllowercase123", False),
        ("NoDigitsHereAtAll", False),
        ("Good-Passw0rd!", True),
    ],
)
def test_password_policy(pw: str, ok: bool) -> None:
    assert (password_problems(pw) == []) is ok


def test_secret_encryption_roundtrip() -> None:
    token = encrypt_secret("sk-test-1234")
    assert "sk-test" not in token
    assert decrypt_secret(token) == "sk-test-1234"
    assert decrypt_secret("garbage") is None


def test_csrf_compare() -> None:
    assert csrf_matches("abc", "abc")
    assert not csrf_matches("abc", "abd")
    assert not csrf_matches(None, "abc")


def test_markdown_escapes_html() -> None:
    out = str(render_markdown('<script>alert(1)</script>\n<img src=x onerror="x">'))
    assert "<script>" not in out and "<img" not in out
    assert "&lt;script&gt;" in out


def test_markdown_structures() -> None:
    md = "### Title\n- a\n- **b**\n\n1. one\n\n| h1 | h2 |\n|---|---|\n| x | y |\n\n```sql\nSELECT 1\n```"
    out = str(render_markdown(md))
    for frag in (
        "<h5>Title</h5>",
        "<ul>",
        "<strong>b</strong>",
        "<ol>",
        "<th>h1</th>",
        "<td>y</td>",
        '<pre class="code" data-lang="sql">',
    ):
        assert frag in out


def test_all_modules_have_guardrails() -> None:
    specs = load_specs()
    assert set(specs) == {
        "career_coach",
        "research_summarizer",
        "sql_assistant",
        "status_report",
        "requirements_analyst",
    }
    for spec in specs.values():
        assert spec.guardrail, spec.id
        assert "<user_input>" in spec.guardrail, f"{spec.id} must treat input as data"
        assert 0 < spec.max_tokens <= 2000


def test_parse_module_requires_front_matter() -> None:
    with pytest.raises(ValueError):
        parse_module("# no front matter")


@pytest.mark.parametrize(
    "sql",
    [
        "DELETE FROM tickets",
        "SELECT 1; DROP TABLE plans",
        "PRAGMA table_info(plans)",
        "ATTACH 'x.db' AS x",
        "",
        "SELECT * FROM plans WHERE name = 'x' UNION SELECT 1; INSERT",
    ],
)
def test_sql_validator_rejects(sql: str) -> None:
    with pytest.raises(sample_data.QueryRejected):
        sample_data.validate_sql(sql)


def test_sql_runs_readonly_select(tmp_path: object) -> None:
    cols, rows = sample_data.run_readonly(
        "SELECT name, monthly_price FROM plans ORDER BY id LIMIT 2;"
    )
    assert cols == ["name", "monthly_price"]
    assert len(rows) == 2


def test_sql_row_cap() -> None:
    _, rows = sample_data.run_readonly("SELECT * FROM customers")
    assert len(rows) == sample_data.MAX_ROWS


def test_sql_authorizer_blocks_writes_even_in_cte() -> None:
    with pytest.raises(sample_data.QueryRejected):
        sample_data.run_readonly(
            "WITH x AS (SELECT 1) SELECT * FROM x, sqlite_master WHERE 0 = 1 "
            "UNION SELECT load_extension('evil'), 1, 1, 1, 1, 1"
        )
