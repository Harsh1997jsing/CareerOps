from datetime import datetime
from unittest.mock import MagicMock, patch

from app.sources.greenhouse import fetch_jobs, normalize_job

RAW_JOB = {
    "id": 12345,
    "title": "Backend Engineer",
    "location": {"name": "Bengaluru, Karnataka"},
    "absolute_url": "https://boards.greenhouse.io/acme/jobs/12345",
    "content": "<p>Build <b>great</b> software.</p>",
    "updated_at": "2024-05-01T12:00:00-04:00",
    "metadata": [{"name": "Employment Type", "value": "Full-time"}],
}


def test_normalize_job_maps_fields():
    job = normalize_job("Acme", RAW_JOB)

    assert job["source"] == "greenhouse"
    assert job["source_job_id"] == "12345"
    assert job["company"] == "Acme"
    assert job["title"] == "Backend Engineer"
    assert job["location"] == "Bangalore"
    assert job["url"] == "https://boards.greenhouse.io/acme/jobs/12345"
    assert job["description"] == "Build  great  software."
    assert job["employment_type"] == "Full-time"
    assert job["posted_at"] == datetime.fromisoformat("2024-05-01T12:00:00-04:00")
    assert len(job["description_hash"]) == 64


def test_normalize_job_handles_missing_metadata():
    raw = {**RAW_JOB, "metadata": []}
    job = normalize_job("Acme", raw)
    assert job["employment_type"] is None


def test_normalize_job_handles_missing_updated_at():
    raw = {**RAW_JOB, "updated_at": None}
    job = normalize_job("Acme", raw)
    assert job["posted_at"] is None


def _mock_response(payload):
    response = MagicMock()
    response.json.return_value = payload
    response.raise_for_status.return_value = None
    return response


def test_fetch_jobs_returns_normalized_jobs():
    with patch("app.sources.greenhouse.requests.get", return_value=_mock_response({"jobs": [RAW_JOB]})) as mock_get:
        jobs = fetch_jobs("acme", "Acme")

    assert len(jobs) == 1
    assert jobs[0]["title"] == "Backend Engineer"
    args, kwargs = mock_get.call_args
    assert "acme" in args[0]
    assert kwargs["params"] == {"content": "true"}


def test_fetch_jobs_caps_at_max_per_run():
    many_jobs = [{**RAW_JOB, "id": i} for i in range(75)]
    with patch("app.sources.greenhouse.requests.get", return_value=_mock_response({"jobs": many_jobs})):
        jobs = fetch_jobs("acme", "Acme", limit=1000)

    assert len(jobs) == 50


def test_fetch_jobs_respects_smaller_explicit_limit():
    many_jobs = [{**RAW_JOB, "id": i} for i in range(10)]
    with patch("app.sources.greenhouse.requests.get", return_value=_mock_response({"jobs": many_jobs})):
        jobs = fetch_jobs("acme", "Acme", limit=3)

    assert len(jobs) == 3
