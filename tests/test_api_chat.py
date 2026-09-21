from unittest.mock import AsyncMock, MagicMock, patch

from fastapi.testclient import TestClient

from app.api.dependencies import get_current_user, get_db
from app.api.main import app
from app.llm.schemas import ChatSearchIntent
from app.models import ChatSearchResult
from tests.conftest import FAKE_USER_CONTEXT

client = TestClient(app)
app.dependency_overrides[get_db] = lambda: iter([MagicMock()])
app.dependency_overrides[get_current_user] = lambda: FAKE_USER_CONTEXT


def _intent(**overrides):
    defaults = dict(
        query="backend engineer", location=None, experience=None,
        posted_within_days=None, company=None, ready_to_search=True,
        clarification_question=None,
    )
    return ChatSearchIntent(**{**defaults, **overrides})


def _staged_row(**overrides):
    defaults = dict(
        id=1, session_id="sess-1", source="jobo", source_job_id="j1", company="Acme",
        title="Backend Engineer", location="Bangalore", url="https://example.com/apply/j1",
        description="Build things", employment_type="Full-time", salary_min=None,
        salary_max=None, posted_at=None,
    )
    return ChatSearchResult(**{**defaults, **overrides})


def test_send_message_requires_authentication():
    app.dependency_overrides.pop(get_current_user, None)
    try:
        response = client.post("/chat/message", json={"session_id": "sess-1", "message": "find me a job"})
    finally:
        app.dependency_overrides[get_current_user] = lambda: FAKE_USER_CONTEXT

    assert response.status_code == 401


def test_send_message_asks_for_clarification_when_not_ready():
    intent = _intent(query="", ready_to_search=False, clarification_question="What role are you looking for?")
    with patch("app.api.routes.chat.chat_search.extract_intent", return_value=intent), \
         patch("app.api.routes.chat.chat_search.run_search") as mock_search:
        response = client.post("/chat/message", json={"session_id": "sess-1", "message": "find me a job"})

    assert response.status_code == 200
    body = response.json()
    assert body["ready"] is False
    assert body["reply"] == "What role are you looking for?"
    assert body["results"] == []
    mock_search.assert_not_called()


def test_send_message_searches_and_stages_when_ready():
    intent = _intent()
    staged = [_staged_row()]
    with patch("app.api.routes.chat.chat_search.extract_intent", return_value=intent), \
         patch("app.api.routes.chat.chat_search.run_search", AsyncMock(return_value=[{"source": "jobo"}])), \
         patch("app.api.routes.chat.chat_search.stage_results", AsyncMock(return_value=staged)):
        response = client.post(
            "/chat/message", json={"session_id": "sess-1", "message": "backend engineer in Bangalore"}
        )

    assert response.status_code == 200
    body = response.json()
    assert body["ready"] is True
    assert "Found 1 matching job" in body["reply"]
    assert len(body["results"]) == 1
    assert body["results"][0]["company"] == "Acme"


def test_send_message_replies_when_nothing_found():
    intent = _intent()
    with patch("app.api.routes.chat.chat_search.extract_intent", return_value=intent), \
         patch("app.api.routes.chat.chat_search.run_search", AsyncMock(return_value=[])), \
         patch("app.api.routes.chat.chat_search.stage_results", AsyncMock(return_value=[])):
        response = client.post("/chat/message", json={"session_id": "sess-1", "message": "backend engineer"})

    assert response.json()["reply"] == "No matches found for that search — try loosening a filter."


def test_list_results_returns_staged_rows():
    with patch("app.api.routes.chat.chat_search.get_staged_results", AsyncMock(return_value=[_staged_row()])):
        response = client.get("/chat/results/sess-1")

    assert response.status_code == 200
    body = response.json()
    assert len(body) == 1
    assert body[0]["title"] == "Backend Engineer"
