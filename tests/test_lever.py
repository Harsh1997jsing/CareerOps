from datetime import datetime
from unittest.mock import MagicMock, patch

from app.sources.lever import fetch_jobs, normalize_job

RAW_JOB = {
    "id": "abc-123",
    "text": "Backend Engineer",
    "categories": {"location": "Remote - India", "commitment": "Full-time"},
    "hostedUrl": "https://jobs.lever.co/acme/abc-123",
    "descriptionPlain": "Build great software.",
    "createdAt": 1714608000000,  # 2024-05-02T00:00:00Z in ms
}


def test_normalize_job_maps_fields():
    job = normalize_job("Acme", RAW_JOB)

    assert job["source"] == "lever"
    assert job["source_job_id"] == "abc-123"
    assert job["company"] == "Acme"
    assert job["title"] == "Backend Engineer"
    assert job["location"] == "Remote"
    assert job["url"] == "https://jobs.lever.co/acme/abc-123"
    assert job["description"] == "Build great software."
    assert job["employment_type"] == "Full-time"
    assert job["posted_at"] == datetime.fromtimestamp(1714608000000 / 1000)
    assert len(job["description_hash"]) == 64


def test_normalize_job_handles_missing_created_at():
    raw = {**RAW_JOB, "createdAt": None}
    job = normalize_job("Acme", raw)
    assert job["posted_at"] is None


def test_normalize_job_falls_back_to_html_description():
    raw = {**RAW_JOB, "descriptionPlain": None, "description": "<p>HTML desc</p>"}
    job = normalize_job("Acme", raw)
    assert job["description"] == "HTML desc"


def _mock_response(payload):
    response = MagicMock()
    response.json.return_value = payload
    response.raise_for_status.return_value = None
    return response


def test_fetch_jobs_returns_normalized_jobs():
    with patch("app.sources.lever.requests.get", return_value=_mock_response([RAW_JOB])) as mock_get:
        jobs = fetch_jobs("acme", "Acme")

    assert len(jobs) == 1
    assert jobs[0]["title"] == "Backend Engineer"
    args, kwargs = mock_get.call_args
    assert "acme" in args[0]
    assert kwargs["params"] == {"mode": "json"}


def test_fetch_jobs_caps_at_max_per_run():
    many_jobs = [{**RAW_JOB, "id": str(i)} for i in range(75)]
    with patch("app.sources.lever.requests.get", return_value=_mock_response(many_jobs)):
        jobs = fetch_jobs("acme", "Acme", limit=1000)

    assert len(jobs) == 50
