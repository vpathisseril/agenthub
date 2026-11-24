from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)

EXPECTED_MODULES = {
    "career_coach",
    "requirements_analyst",
    "research_summarizer",
    "sql_assistant",
    "status_report",
}


def test_health_ok() -> None:
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"


def test_all_starter_modules_have_guardrails() -> None:
    assert set(client.get("/health").json()["modules"]) == EXPECTED_MODULES
