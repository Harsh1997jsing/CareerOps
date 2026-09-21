from unittest.mock import AsyncMock, MagicMock, patch

from fastapi.testclient import TestClient

from app.api.dependencies import get_current_user, get_db
from app.api.main import app
from tests.conftest import FAKE_USER_CONTEXT

client = TestClient(app)
app.dependency_overrides[get_db] = lambda: iter([MagicMock()])
app.dependency_overrides[get_current_user] = lambda: FAKE_USER_CONTEXT

JOB = {
    "source": "indeed",
    "source_job_id": "j1",
    "company": "Acme",
    "title": "Backend Engineer",
    "location": "Bangalore",
    "url": "https://example.com/apply/j1",
    "description": "Build things",
    "description_hash": "a" * 64,
    "employment_type": "Full-time",
    "posted_at": None,
    "salary_min": None,
    "salary_max": None,
}


def test_scrape_jobspy_requires_authentication():
    app.dependency_overrides.pop(get_current_user, None)
    try:
        response = client.post("/scrape/jobspy", json={"search_term": "backend engineer"})
    finally:
        app.dependency_overrides[get_current_user] = lambda: FAKE_USER_CONTEXT

    assert response.status_code == 401


def test_scrape_jobspy_returns_results_without_inserting():
    # No insert_jobs call exists on this route at all anymore —
    # search-then-select-then-save, same as Explore and /targets/search.
    with patch("app.api.routes.scrape.jobspy_source.fetch_jobs", return_value=[JOB]) as mock_fetch:
        response = client.post(
            "/scrape/jobspy", json={"search_term": "backend engineer", "location": "Bangalore"}
        )

    assert response.status_code == 200
    body = response.json()
    assert len(body) == 1
    assert body[0]["company"] == "Acme"
    mock_fetch.assert_called_once()


def test_scrape_jobspy_returns_empty_list_when_nothing_matches():
    with patch("app.api.routes.scrape.jobspy_source.fetch_jobs", return_value=[]):
        response = client.post("/scrape/jobspy", json={"search_term": "nonexistent role xyz"})

    assert response.json() == []


def test_scrape_jobspy_forwards_experience_filter():
    with patch("app.api.routes.scrape.jobspy_source.fetch_jobs", return_value=[JOB]) as mock_fetch:
        response = client.post(
            "/scrape/jobspy", json={"search_term": "backend engineer", "experience": "senior"}
        )

    assert response.status_code == 200
    mock_fetch.assert_called_once_with("backend engineer", None, None, 50, "senior")
