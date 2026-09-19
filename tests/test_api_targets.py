from unittest.mock import AsyncMock, MagicMock, mock_open, patch

from fastapi.testclient import TestClient

from app.api.dependencies import get_current_user, get_db
from app.api.main import app
from tests.conftest import FAKE_USER_CONTEXT

client = TestClient(app)
app.dependency_overrides[get_db] = lambda: iter([MagicMock()])
app.dependency_overrides[get_current_user] = lambda: FAKE_USER_CONTEXT

COMPANIES_YAML = """
greenhouse:
  - board_token: acme
    company: Acme
lever:
  - company_slug: beta-co
    company: Beta Co
"""


def test_list_targets_requires_authentication():
    app.dependency_overrides.pop(get_current_user, None)
    try:
        response = client.get("/targets")
    finally:
        app.dependency_overrides[get_current_user] = lambda: FAKE_USER_CONTEXT

    assert response.status_code == 401


def test_list_targets_flattens_greenhouse_and_lever():
    with patch("builtins.open", mock_open(read_data=COMPANIES_YAML)):
        response = client.get("/targets")

    assert response.status_code == 200
    body = response.json()
    assert {"source": "greenhouse", "company": "Acme", "identifier": "acme"} in body
    assert {"source": "lever", "company": "Beta Co", "identifier": "beta-co"} in body


JOB = {
    "source": "greenhouse",
    "source_job_id": "j1",
    "company": "Acme",
    "title": "Backend Engineer",
    "location": "Bangalore",
    "url": "https://example.com/apply/j1",
    "description": "Build things",
    "employment_type": "Full-time",
}


def test_search_targets_requires_authentication():
    app.dependency_overrides.pop(get_current_user, None)
    try:
        response = client.post("/targets/search")
    finally:
        app.dependency_overrides[get_current_user] = lambda: FAKE_USER_CONTEXT

    assert response.status_code == 401


def test_search_targets_returns_results_without_inserting():
    # search_all() only fetches — no insert_jobs call exists on this route
    # at all (search-then-select-then-save, same as Explore).
    with patch("app.api.routes.targets.targets.search_all", AsyncMock(return_value=[JOB])) as mock_search:
        response = client.post("/targets/search")

    assert response.status_code == 200
    body = response.json()
    assert len(body) == 1
    assert body[0]["company"] == "Acme"
    mock_search.assert_called_once()
