"""Provider adapters against mocked HTTP (no network, no spend)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import httpx
import pytest

from app.llm import providers
from app.llm.base import LLMError, LLMRequest, estimate_cost
from app.services import sample_data

REQ = LLMRequest(
    system="sys", user="<user_input>\nhi\n</user_input>", model="m", max_tokens=50, temperature=0.1
)


class _Resp:
    def __init__(self, status: int, data: dict[str, Any]) -> None:
        self.status_code, self._data = status, data

    def json(self) -> dict[str, Any]:
        return self._data


def _mock(
    monkeypatch: pytest.MonkeyPatch, status: int, data: dict[str, Any], seen: dict[str, Any]
) -> None:
    def fake_post(
        url: str, headers: dict[str, str], json: dict[str, Any], timeout: object
    ) -> _Resp:
        seen.update(url=url, headers=headers, body=json)
        return _Resp(status, data)

    monkeypatch.setattr(providers.httpx, "post", fake_post)


def test_anthropic(monkeypatch: pytest.MonkeyPatch) -> None:
    seen: dict[str, Any] = {}
    _mock(
        monkeypatch,
        200,
        {
            "content": [{"type": "text", "text": "ok"}],
            "usage": {"input_tokens": 5, "output_tokens": 2},
        },
        seen,
    )
    r = providers.AnthropicProvider().complete(REQ, "k")
    assert (r.text, r.tokens_in, r.tokens_out) == ("ok", 5, 2)
    assert seen["headers"]["x-api-key"] == "k" and seen["body"]["system"] == "sys"


def test_openai(monkeypatch: pytest.MonkeyPatch) -> None:
    seen: dict[str, Any] = {}
    _mock(
        monkeypatch,
        200,
        {
            "choices": [{"message": {"content": "hey"}}],
            "usage": {"prompt_tokens": 7, "completion_tokens": 3},
        },
        seen,
    )
    r = providers.OpenAIProvider().complete(REQ, "k")
    assert (r.text, r.tokens_in, r.tokens_out) == ("hey", 7, 3)
    assert seen["body"]["messages"][0] == {"role": "system", "content": "sys"}


def test_gemini(monkeypatch: pytest.MonkeyPatch) -> None:
    seen: dict[str, Any] = {}
    _mock(
        monkeypatch,
        200,
        {
            "candidates": [{"content": {"parts": [{"text": "g"}]}}],
            "usageMetadata": {"promptTokenCount": 4, "candidatesTokenCount": 1},
        },
        seen,
    )
    r = providers.GeminiProvider().complete(REQ, "k")
    assert (r.text, r.tokens_in, r.tokens_out) == ("g", 4, 1)
    assert seen["url"].endswith("/m:generateContent") and seen["headers"]["x-goog-api-key"] == "k"


@pytest.mark.parametrize(("status", "msg"), [(401, "API key"), (429, "rate limit"), (500, "500")])
def test_errors_are_user_safe(monkeypatch: pytest.MonkeyPatch, status: int, msg: str) -> None:
    _mock(monkeypatch, status, {}, {})
    with pytest.raises(LLMError, match=msg):
        providers.AnthropicProvider().complete(REQ, "k")


def test_network_error(monkeypatch: pytest.MonkeyPatch) -> None:
    def fail(*a: object, **k: object) -> None:
        raise httpx.ConnectError("down")

    monkeypatch.setattr(providers.httpx, "post", fail)
    with pytest.raises(LLMError, match="reach"):
        providers.OpenAIProvider().complete(REQ, "k")


def test_cost_estimate() -> None:
    assert estimate_cost("anthropic", 1_000_000, 0) == 1.0
    assert estimate_cost("demo", 10_000, 10_000) == 0.0


def test_build_sample_db(tmp_path: Path) -> None:
    path = sample_data.build_sample_db(tmp_path / "s.db")
    cols, rows = sample_data.run_readonly("SELECT COUNT(*) AS n FROM customers", path)
    assert cols == ["n"] and rows[0][0] == 500
    assert sample_data.build_sample_db(path) == path  # idempotent
