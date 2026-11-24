"""Career Coach v1.1: attachments, labelled inputs, model list, provider errors (AC-CC-*)."""

from __future__ import annotations

import io
import re
from typing import Any

import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.security import encrypt_secret
from app.llm import catalog, providers
from app.llm.base import LLMError, LLMRequest, LLMResponse
from app.models import AgentConfig, ApiKey
from app.services import agents, approval
from app.services.attachments import AttachmentError, extract_text
from tests.conftest import csrf, signup

RESUME = (
    "Jane Doe\nDirector, Data Platform, Acme Telecom 2019-2026\nLed 40 engineers; cut costs 30%."
)


def _pdf_bytes(text: str) -> bytes:
    from reportlab.pdfgen import canvas

    buf = io.BytesIO()
    c = canvas.Canvas(buf)
    for i, line in enumerate(text.splitlines()):
        c.drawString(72, 750 - 14 * i, line)
    c.save()
    return buf.getvalue()


def _docx_bytes(text: str) -> bytes:
    from docx import Document

    d = Document()
    for line in text.splitlines():
        d.add_paragraph(line)
    buf = io.BytesIO()
    d.save(buf)
    return buf.getvalue()


# --- attachments ---
@pytest.mark.parametrize(
    ("name", "make"),
    [("cv.pdf", _pdf_bytes), ("cv.docx", _docx_bytes), ("cv.txt", lambda t: t.encode())],
)
def test_extract_text_formats(name: str, make: Any) -> None:
    out = extract_text(name, make(RESUME))
    assert "Director, Data Platform" in out and "cut costs 30%" in out


@pytest.mark.parametrize(
    ("name", "data", "msg"),
    [
        ("cv.exe", b"MZ", "use a PDF"),
        ("cv.txt", b"", "empty"),
        ("cv.txt", b"x" * (2 * 1024 * 1024 + 1), "2 MB"),
        ("cv.pdf", b"not a pdf", "Couldn't read"),
        ("cv.docx", b"not a zip", "damaged"),
        ("cv.txt", b"   \n  ", "No text"),
    ],
)
def test_extract_text_rejects(name: str, data: bytes, msg: str) -> None:
    with pytest.raises(AttachmentError, match=msg):
        extract_text(name, data)


# --- end to end through HTTP (AC-CC-1..3) ---
def _builder(client: TestClient) -> tuple[str, str]:
    page = client.get("/app/modules/career_coach").text
    cfg = re.search(r'name="config_id" value="(\d+)"', page)
    assert cfg and 'name="resume_file"' in page and 'name="job_description_file"' in page
    assert 'hx-encoding="multipart/form-data"' in page
    return cfg.group(1), csrf(client, "/app")


def test_run_with_attached_resume_and_pasted_jd(client: TestClient) -> None:
    signup(client)
    cfg_id, token = _builder(client)
    r = client.post(
        "/app/modules/career_coach/run",
        data={
            "config_id": cfg_id,
            "task": "Match score and gap analysis only",
            "job_description": "Executive Director, Data Platform. PMP required.",
        },
        files={"resume_file": ("resume.pdf", _pdf_bytes(RESUME), "application/pdf")},
        headers={"X-CSRF-Token": token, "HX-Request": "true"},
    )
    assert r.status_code == 200
    assert "Read “resume.pdf” for your resume" in r.text
    assert "Match summary" in r.text  # demo model answered


def test_resume_required(client: TestClient) -> None:
    signup(client)
    cfg_id, token = _builder(client)
    r = client.post(
        "/app/modules/career_coach/run",
        data={"config_id": cfg_id, "notes": "hi"},
        headers={"X-CSRF-Token": token, "HX-Request": "true"},
    )
    assert "Please add your resume" in r.text


def test_bad_attachment_message(client: TestClient) -> None:
    signup(client)
    cfg_id, token = _builder(client)
    r = client.post(
        "/app/modules/career_coach/run",
        data={"config_id": cfg_id},
        files={"resume_file": ("cv.exe", b"MZ", "application/octet-stream")},
        headers={"X-CSRF-Token": token, "HX-Request": "true"},
    )
    assert "use a PDF" in r.text


def test_labelled_sections_reach_the_model(db: Session, monkeypatch: pytest.MonkeyPatch) -> None:
    from starlette.datastructures import FormData

    from app.services.inputs import compose_input
    from app.services.modules_registry import get_spec

    spec = get_spec("career_coach")
    assert spec is not None
    import asyncio

    text, notes = asyncio.run(
        compose_input(
            spec,
            FormData(
                [("task", "not-an-option"), ("resume", RESUME), ("job_description", "JD text")]
            ),
        )
    )
    assert text.startswith("TASK:\nFull review") and "RESUME:\nJane Doe" in text
    assert "JOB DESCRIPTION:\nJD text" in text and "NOTES" not in text and notes == []


# --- model dropdown (AC-CC-4) ---
def test_model_dropdown_curated_without_key(client: TestClient) -> None:
    signup(client)
    page = client.get("/app/modules/career_coach").text
    assert '<select id="model"' in page and "claude-sonnet-5-5" in page
    r = client.get("/app/models?provider=openai")
    assert "Provider default (gpt-6-luna)" in r.text and "gpt-6.1-sol" in r.text
    assert (
        "may be unavailable"
        in client.get("/app/models?provider=gemini&selected=gemini-2.5-flash").text
    )
    assert client.get("/app/models?provider=nope").status_code == 400


def test_model_list_live_with_key(monkeypatch: pytest.MonkeyPatch) -> None:
    catalog.clear_cache()
    monkeypatch.setattr(
        catalog, "_fetch", lambda p, k: ["claude-x-9", "claude-haiku-5-5", "claude-tts-1"]
    )
    ids, live = catalog.list_models("anthropic", "sk-ant-123456")
    assert live and ids == ["claude-haiku-5-5", "claude-x-9"]  # curated first, tts filtered

    def boom(p: str, k: str) -> list[str]:
        raise httpx.ConnectError("down")

    catalog.clear_cache()
    monkeypatch.setattr(catalog, "_fetch", boom)
    assert catalog.list_models("anthropic", "sk-ant-123456") == (
        catalog.CURATED["anthropic"],
        False,
    )


# --- provider errors (AC-CC-5) ---
class _Resp:
    def __init__(self, status: int, data: dict[str, Any]) -> None:
        self.status_code, self._d = status, data

    def json(self) -> dict[str, Any]:
        return self._d


REQ = LLMRequest("sys", "<user_input>\nx\n</user_input>", "m-1", 50, 0.4)


def test_error_messages_are_specific(monkeypatch: pytest.MonkeyPatch) -> None:
    cases = [
        (400, "API key not valid. Please pass a valid API key.", "rejected the API key"),
        (404, "models/m-1 is not found", "isn't available for this key"),
        (400, "max_tokens: must be positive", "Provider error 400: max_tokens"),
    ]
    for status, msg, expect in cases:
        monkeypatch.setattr(
            providers.httpx,
            "post",
            lambda *a, s=status, m=msg, **k: _Resp(s, {"error": {"message": m}}),
        )
        with pytest.raises(LLMError, match=expect):
            providers.GeminiProvider().complete(REQ, "k")


def test_temperature_rejected_is_retried_without_it(monkeypatch: pytest.MonkeyPatch) -> None:
    bodies: list[dict[str, Any]] = []

    def post(url: str, headers: dict[str, str], json: dict[str, Any], timeout: object) -> _Resp:
        bodies.append(json)
        if "temperature" in json:
            return _Resp(400, {"error": {"message": "Unsupported value: 'temperature'"}})
        return _Resp(200, {"choices": [{"message": {"content": "ok"}}], "usage": {}})

    monkeypatch.setattr(providers.httpx, "post", post)
    assert providers.OpenAIProvider().complete(REQ, "k").text == "ok"
    assert "temperature" in bodies[0] and "temperature" not in bodies[1]


def test_retired_model_falls_back_to_default(db: Session, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(get_settings(), "llm_fake_mode", False)
    user = approval.register(db, "f@example.com", "F", "Str0ng-Password-1")
    db.add(
        ApiKey(
            user_id=user.id,
            provider="anthropic",
            encrypted_key=encrypt_secret("sk-ant-k"),
            last4="t-k",
        )
    )
    cfg = AgentConfig(
        user_id=user.id,
        module_id="career_coach",
        name="t",
        provider="anthropic",
        model="claude-retired-1",
    )
    db.add(cfg)
    db.commit()
    seen: list[str] = []

    class Stub:
        name = "anthropic"

        def complete(self, req: LLMRequest, api_key: str) -> LLMResponse:
            seen.append(req.model)
            if req.model == "claude-retired-1":
                raise LLMError("gone", kind="model")
            return LLMResponse("### Match summary", 10, 5, req.model)

    monkeypatch.setitem(agents.PROVIDERS, "anthropic", Stub())
    result = agents.run_agent(db, user, cfg, "RESUME:\nx")
    assert seen == ["claude-retired-1", "claude-haiku-5-5"]
    assert result.model == "claude-haiku-5-5" and any("was used" in n for n in result.notes)


def test_fetch_parses_each_provider(monkeypatch: pytest.MonkeyPatch) -> None:
    payloads = {
        "anthropic.com": {"data": [{"id": "claude-haiku-5-5"}]},
        "openai.com": {
            "data": [{"id": "gpt-6-luna"}, {"id": "gpt-4o-2024-08-06"}, {"id": "dall-e-3"}]
        },
        "googleapis.com": {
            "models": [
                {
                    "name": "models/gemini-3.5-flash",
                    "supportedGenerationMethods": ["generateContent"],
                },
                {"name": "models/text-embedding-9", "supportedGenerationMethods": ["embedContent"]},
            ]
        },
    }

    class R:
        def __init__(self, d: dict[str, Any]) -> None:
            self.d = d

        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict[str, Any]:
            return self.d

    def get(url: str, headers: dict[str, str], timeout: object) -> R:
        return R(next(v for k, v in payloads.items() if k in url))

    monkeypatch.setattr(catalog.httpx, "get", get)
    assert catalog._fetch("anthropic", "k") == ["claude-haiku-5-5"]
    assert catalog._fetch("openai", "k") == ["gpt-6-luna"]  # dated snapshot + non-chat dropped
    assert catalog._fetch("gemini", "k") == ["gemini-3.5-flash"]
    assert catalog._fetch("other", "k") == []


def test_version_bump_refreshes_module_limits(db: Session) -> None:
    from app.models import Module
    from app.services.modules_registry import sync_modules

    m = db.get(Module, "career_coach")
    assert m is not None
    m.version, m.max_tokens = "1.0.0", 1200
    db.commit()
    sync_modules(db)
    db.refresh(m)
    assert (m.version, m.max_tokens) == ("1.1.0", 2000)


def test_bootstrap_retries_when_db_drops(monkeypatch: pytest.MonkeyPatch) -> None:
    from sqlalchemy.exc import OperationalError

    import app.main as main

    calls: list[int] = []

    def flaky() -> None:
        calls.append(1)
        if len(calls) < 3:
            raise OperationalError("SELECT 1", {}, Exception("terminating connection"))

    monkeypatch.setattr(main, "_bootstrap", flaky)
    monkeypatch.setattr(main.time, "sleep", lambda s: None)
    main.bootstrap()
    assert len(calls) == 3
    calls.clear()
    monkeypatch.setattr(
        main,
        "_bootstrap",
        lambda: (_ for _ in ()).throw(OperationalError("x", {}, Exception("down"))),
    )
    with pytest.raises(OperationalError):
        main.bootstrap(attempts=2)
