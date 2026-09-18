from datetime import date, datetime

import pandas as pd
from unittest.mock import patch

from app.sources.jobspy_source import fetch_jobs, normalize_job

RAW_ROW = {
    "id": "in-123",
    "site": "indeed",
    "title": "Backend Engineer",
    "company": "Acme",
    "location": "Bengaluru, Karnataka, IN",
    "job_url": "https://indeed.com/viewjob?jk=123",
    "description": "<p>Build <b>great</b> software.</p>",
    "job_type": "fulltime",
    "date_posted": date(2024, 5, 1),
    "min_amount": 1200000.0,
    "max_amount": 1800000.0,
}


def test_normalize_job_maps_fields():
    job = normalize_job(RAW_ROW)

    assert job["source"] == "indeed"
    assert job["source_job_id"] == "in-123"
    assert job["company"] == "Acme"
    assert job["title"] == "Backend Engineer"
    assert job["location"] == "Bangalore"
    assert job["url"] == "https://indeed.com/viewjob?jk=123"
    assert job["description"] == "Build  great  software."
    assert job["employment_type"] == "Full-time"
    assert job["posted_at"] == datetime(2024, 5, 1)
    assert job["salary_min"] == 1200000
    assert job["salary_max"] == 1800000
    assert len(job["description_hash"]) == 64


def test_normalize_job_handles_missing_salary():
    row = {**RAW_ROW, "min_amount": None, "max_amount": float("nan")}
    job = normalize_job(row)
    assert job["salary_min"] is None
    assert job["salary_max"] is None


def test_normalize_job_falls_back_to_job_url_direct():
    row = {**RAW_ROW, "job_url": None, "job_url_direct": "https://example.com/job/123"}
    job = normalize_job(row)
    assert job["url"] == "https://example.com/job/123"


def test_fetch_jobs_drops_linkedin_even_if_requested():
    df = pd.DataFrame([RAW_ROW])
    with patch("app.sources.jobspy_source.scrape_jobs", return_value=df) as mock_scrape:
        jobs = fetch_jobs("backend engineer", sites=["indeed", "linkedin"])

    assert len(jobs) == 1
    called_sites = mock_scrape.call_args.kwargs["site_name"]
    assert "linkedin" not in called_sites
    assert called_sites == ["indeed"]


def test_fetch_jobs_defaults_to_all_allowed_sites():
    df = pd.DataFrame([RAW_ROW])
    with patch("app.sources.jobspy_source.scrape_jobs", return_value=df) as mock_scrape:
        fetch_jobs("backend engineer")

    called_sites = mock_scrape.call_args.kwargs["site_name"]
    assert "linkedin" not in called_sites
    assert set(called_sites) == {"indeed", "glassdoor", "naukri", "zip_recruiter", "google"}


def test_fetch_jobs_returns_empty_list_when_only_linkedin_requested():
    with patch("app.sources.jobspy_source.scrape_jobs") as mock_scrape:
        jobs = fetch_jobs("backend engineer", sites=["linkedin"])

    assert jobs == []
    mock_scrape.assert_not_called()


def test_fetch_jobs_returns_empty_list_for_empty_results():
    with patch("app.sources.jobspy_source.scrape_jobs", return_value=pd.DataFrame()):
        jobs = fetch_jobs("backend engineer")

    assert jobs == []


def test_fetch_jobs_caps_at_max_per_run():
    many_rows = [{**RAW_ROW, "id": f"in-{i}"} for i in range(75)]
    df = pd.DataFrame(many_rows)
    with patch("app.sources.jobspy_source.scrape_jobs", return_value=df):
        jobs = fetch_jobs("backend engineer", results_wanted=1000)

    assert len(jobs) == 50
