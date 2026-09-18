from unittest.mock import AsyncMock, MagicMock, patch

from fastapi.testclient import TestClient

from app.api.dependencies import get_current_user, get_db
from app.api.main import app
from app.sources.mcp.capabilities import build_capability_matrix
from mcp.types import Tool
from tests.conftest import FAKE_USER_CONTEXT

client = TestClient(app)
app.dependency_overrides[get_db] = lambda: iter([MagicMock()])
app.dependency_overrides[get_current_user] = lambda: FAKE_USER_CONTEXT

RESULT = {
    "source": "jobo",
    "source_job_id": "j1",
    "company": "Acme",
    "title": "Backend Engineer",
    "location": "Bangalore",
    "url": "https://example.com/apply/j1",
    "description": "Build things",
    "description_hash": "a" * 64,
    "employment_type": "Full-time",
    "posted_at": None,
    "salary_min": 1000000,
    "salary_max": 1500000,
}


def test_search_requires_authentication():
    # Audit finding F1: /explore/* required no auth at all.
    app.dependency_overrides.pop(get_current_user, None)
    try:
        response = client.post("/explore/search", json={"query": "backend engineer"})
    finally:
        app.dependency_overrides[get_current_user] = lambda: FAKE_USER_CONTEXT

    assert response.status_code == 401


def test_search_returns_normalized_results():
    with patch("app.api.routes.explore.mcp_explore.search", AsyncMock(return_value=[RESULT])) as mock_search:
        response = client.post("/explore/search", json={"query": "backend engineer", "filters": {"location": "Bangalore"}})

    assert response.status_code == 200
    body = response.json()
    assert body[0]["source"] == "jobo"
    assert body[0]["company"] == "Acme"
    mock_search.assert_called_once_with("backend engineer", {"location": "Bangalore"})


def test_search_defaults_filters_to_empty_dict():
    with patch("app.api.routes.explore.mcp_explore.search", AsyncMock(return_value=[])) as mock_search:
        client.post("/explore/search", json={"query": "backend engineer"})

    mock_search.assert_called_once_with("backend engineer", {})


def test_capabilities_returns_flags_per_source():
    matrix = build_capability_matrix([Tool(name="search_jobs", input_schema={"type": "object", "properties": {}})])
    with patch("app.api.routes.explore.mcp_explore.get_all_capabilities", AsyncMock(return_value={"jobo": matrix})):
        response = client.get("/explore/capabilities")

    assert response.status_code == 200
    body = response.json()
    assert body["jobo"]["flags"]["search"] is True


def test_save_inserts_job_and_reports_inserted_true():
    with patch("app.api.routes.explore.insert_jobs", AsyncMock(return_value=1)) as mock_insert:
        response = client.post("/explore/save", json=RESULT)

    assert response.status_code == 200
    assert response.json()["inserted"] is True
    job = mock_insert.call_args[0][1][0]
    assert job["source"] == "jobo"
    assert job["description_hash"] != RESULT["description_hash"]  # recomputed server-side, not trusted


def test_save_reports_inserted_false_for_a_duplicate():
    with patch("app.api.routes.explore.insert_jobs", AsyncMock(return_value=0)):
        response = client.post("/explore/save", json=RESULT)

    assert response.json()["inserted"] is False
