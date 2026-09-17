from unittest.mock import MagicMock

from app.sources.common import (
    description_hash,
    insert_jobs,
    normalize_employment_type,
    normalize_location,
    strip_html,
)


def test_strip_html_removes_tags():
    assert strip_html("<p>Hello <b>world</b></p>") == "Hello  world"


def test_strip_html_handles_none():
    assert strip_html(None) == ""


def test_description_hash_is_stable_across_whitespace_and_case():
    a = description_hash("Build  Great   Software")
    b = description_hash("build great software")
    assert a == b


def test_description_hash_differs_for_different_text():
    assert description_hash("Job A") != description_hash("Job B")


def test_normalize_location_maps_known_variants():
    assert normalize_location("Remote - India") == "Remote"
    assert normalize_location("Bengaluru, Karnataka") == "Bangalore"
    assert normalize_location("Pune, Maharashtra") == "Pune"
    assert normalize_location("Hyderabad") == "Hyderabad"


def test_normalize_location_passes_through_unrecognized():
    assert normalize_location("San Francisco, CA") == "San Francisco, CA"


def test_normalize_location_handles_empty():
    assert normalize_location("") == ""
    assert normalize_location(None) == ""


def test_normalize_employment_type_maps_known_variants():
    assert normalize_employment_type("full time") == "Full-time"
    assert normalize_employment_type("FULL-TIME") == "Full-time"
    assert normalize_employment_type("Contractor") == "Contract"


def test_normalize_employment_type_passes_through_unrecognized():
    assert normalize_employment_type("Freelance") == "Freelance"


def test_normalize_employment_type_handles_none():
    assert normalize_employment_type(None) is None


JOB = {
    "source": "greenhouse", "source_job_id": "1", "company": "Acme", "title": "Engineer",
    "location": "Remote", "url": "https://example.com", "description": "desc",
    "description_hash": "hash1", "employment_type": "Full-time", "posted_at": None,
}


def test_insert_jobs_returns_zero_for_empty_list():
    mock_engine = MagicMock()
    assert insert_jobs(mock_engine, []) == 0
    mock_engine.begin.assert_not_called()


def test_insert_jobs_sums_rowcount_across_jobs():
    mock_engine = MagicMock()
    mock_conn = MagicMock()
    mock_engine.begin.return_value.__enter__.return_value = mock_conn
    mock_conn.execute.return_value.rowcount = 1

    inserted = insert_jobs(mock_engine, [JOB, {**JOB, "description_hash": "hash2"}])

    assert inserted == 2
    assert mock_conn.execute.call_count == 2


def test_insert_jobs_counts_duplicates_as_zero_rowcount():
    mock_engine = MagicMock()
    mock_conn = MagicMock()
    mock_engine.begin.return_value.__enter__.return_value = mock_conn
    mock_conn.execute.return_value.rowcount = 0  # ON CONFLICT DO NOTHING skipped it

    inserted = insert_jobs(mock_engine, [JOB])

    assert inserted == 0
