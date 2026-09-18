from sqlalchemy import func, select

from app.models import Job
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


async def _job_count(session):
    return await session.scalar(select(func.count()).select_from(Job))


async def test_insert_jobs_returns_zero_for_empty_list(db_session):
    assert await insert_jobs(db_session, []) == 0
    assert await _job_count(db_session) == 0


async def test_insert_jobs_inserts_each_new_job(db_session):
    inserted = await insert_jobs(db_session, [JOB, {**JOB, "description_hash": "hash2"}])

    assert inserted == 2
    assert await _job_count(db_session) == 2


async def test_insert_jobs_skips_a_duplicate_description_hash(db_session):
    await insert_jobs(db_session, [JOB])

    inserted = await insert_jobs(db_session, [JOB])  # same description_hash again

    assert inserted == 0
    assert await _job_count(db_session) == 1


async def test_insert_jobs_inserts_the_rest_of_the_batch_around_a_duplicate(db_session):
    await insert_jobs(db_session, [JOB])

    inserted = await insert_jobs(db_session, [JOB, {**JOB, "description_hash": "hash2"}])

    assert inserted == 1
    assert await _job_count(db_session) == 2
