from datetime import datetime, timedelta, timezone

from app.llm.schemas import JobFitAnalysis
from app.models import GeneratedDocument, JobAnalysis
from app.services.jobs import (
    DEFAULT_JOB_STATUS,
    REJECTED_JOB_STATUS,
    get_job,
    get_job_by_id,
    list_generated_documents,
    list_jobs,
    record_analysis,
    set_job_status,
)
from tests.conftest import make_job


async def _make_analysis(session, job_id, **overrides):
    defaults = dict(
        job_id=job_id, fit_score=82, confidence="high",
        strong_matches=["Python", "FastAPI"], missing_skills=["Kubernetes"], risks=[],
    )
    analysis = JobAnalysis(**{**defaults, **overrides})
    session.add(analysis)
    await session.commit()
    return analysis


async def test_list_jobs_returns_mapped_items(db_session):
    await make_job(db_session)
    await _make_analysis(db_session, job_id=1)

    jobs = await list_jobs(db_session)

    assert len(jobs) == 1
    assert jobs[0].company == "Acme"
    assert jobs[0].fit_score == 82
    assert jobs[0].strong_matches == ["Python", "FastAPI"]
    assert jobs[0].missing_skills == ["Kubernetes"]


async def test_list_jobs_surfaces_posted_at_when_known(db_session):
    posted = datetime(2026, 9, 1)
    await make_job(db_session, posted_at=posted)

    jobs = await list_jobs(db_session)

    assert jobs[0].posted_at == posted


async def test_list_jobs_falls_back_to_collected_at_when_posted_at_unknown(db_session):
    await make_job(db_session, posted_at=None)

    jobs = await list_jobs(db_session)

    assert jobs[0].posted_at is not None  # collected_at, server-set on insert


async def test_list_jobs_defaults_null_analysis_fields_to_empty_list(db_session):
    await make_job(db_session)  # no JobAnalysis row at all

    jobs = await list_jobs(db_session)

    assert jobs[0].fit_score is None
    assert jobs[0].strong_matches == []
    assert jobs[0].missing_skills == []
    assert jobs[0].risks == []


async def test_list_jobs_uses_the_latest_analysis_by_analyzed_at(db_session):
    await make_job(db_session)
    await _make_analysis(db_session, job_id=1, fit_score=40, analyzed_at=datetime(2026, 1, 1))
    await _make_analysis(db_session, job_id=1, fit_score=90, analyzed_at=datetime(2026, 1, 15))

    jobs = await list_jobs(db_session)

    assert jobs[0].fit_score == 90


async def test_list_jobs_passes_status_filter(db_session):
    await make_job(db_session, job_id=1, status="READY_FOR_REVIEW")
    await make_job(db_session, job_id=2, status="REVIEW_REQUIRED")

    jobs = await list_jobs(db_session, status="REVIEW_REQUIRED")

    assert len(jobs) == 1
    assert jobs[0].job_id == 2


async def test_list_jobs_filters_by_description_keyword_case_insensitive(db_session):
    await make_job(db_session, job_id=1, description="Build things with Python and FastAPI.")
    await make_job(db_session, job_id=2, description="Build things with Java and Spring.")

    jobs = await list_jobs(db_session, q="PYTHON")

    assert len(jobs) == 1
    assert jobs[0].job_id == 1


async def test_list_jobs_filters_by_posted_within_days_using_posted_at(db_session):
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    await make_job(db_session, job_id=1, posted_at=now - timedelta(days=1))
    await make_job(db_session, job_id=2, posted_at=now - timedelta(days=30))

    jobs = await list_jobs(db_session, posted_within_days=3)

    assert len(jobs) == 1
    assert jobs[0].job_id == 1


async def test_list_jobs_posted_within_days_falls_back_to_collected_at(db_session):
    # posted_at is None (source never gave one) — should fall back to
    # collected_at (always set server-side at insert) rather than being
    # excluded just because the *employer's* posting date is unknown.
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    await make_job(db_session, job_id=1, posted_at=None, collected_at=now - timedelta(hours=1))
    await make_job(db_session, job_id=2, posted_at=None, collected_at=now - timedelta(days=30))

    jobs = await list_jobs(db_session, posted_within_days=3)

    assert len(jobs) == 1
    assert jobs[0].job_id == 1


async def test_set_job_status_updates_and_commits(db_session):
    job = await make_job(db_session, job_id=1, status=DEFAULT_JOB_STATUS)

    await set_job_status(db_session, job, REJECTED_JOB_STATUS)

    jobs = await list_jobs(db_session, status=REJECTED_JOB_STATUS)
    assert len(jobs) == 1
    assert jobs[0].job_id == 1


async def test_list_generated_documents_returns_mapped_items(db_session):
    await make_job(db_session)
    db_session.add(GeneratedDocument(
        id=9, job_id=1, type="resume", file_path="generated/resume_v1.docx",
        version=1, claim_check_passed=True, ats_check_passed=False,
    ))
    await db_session.commit()

    docs = await list_generated_documents(db_session, job_id=1)

    assert len(docs) == 1
    assert docs[0].type == "resume"
    assert docs[0].claim_check_passed is True
    assert docs[0].ats_check_passed is False


async def test_get_job_returns_none_when_missing(db_session):
    assert await get_job(db_session, job_id=1) is None


async def test_get_job_maps_fields_and_includes_application(db_session):
    from app.models import Application

    await make_job(db_session)
    await _make_analysis(db_session, job_id=1)
    db_session.add(Application(id=5, job_id=1, status="READY_FOR_REVIEW"))
    await db_session.commit()

    job = await get_job(db_session, job_id=1)

    assert job.job_id == 1
    assert job.description == "Build things with Python."
    assert job.strong_matches == ["Python", "FastAPI"]
    assert job.application is not None
    assert job.application.application_id == 5


async def test_get_job_defaults_null_analysis_fields_to_empty_list(db_session):
    await make_job(db_session)  # no analysis, no application

    job = await get_job(db_session, job_id=1)

    assert job.strong_matches == []
    assert job.missing_skills == []
    assert job.risks == []
    assert job.application is None


async def test_record_analysis_persists_a_new_row(db_session):
    job = await make_job(db_session)
    analysis = JobFitAnalysis(
        eligible=True, fit_score=88, confidence="high",
        strong_matches=["Python"], missing_requirements=["Kubernetes"], risks=[], summary="Strong match.",
    )

    row = await record_analysis(db_session, job, analysis)

    assert row.job_id == job.id
    assert row.fit_score == 88
    assert row.confidence == "high"
    assert row.strong_matches == ["Python"]
    # JobFitAnalysis's own field is "missing_requirements" — the ORM
    # column (and the API-facing shape) calls the same data "missing_skills".
    assert row.missing_skills == ["Kubernetes"]


async def test_record_analysis_is_additive_not_a_replace(db_session):
    job = await make_job(db_session)
    old = JobFitAnalysis(
        eligible=True, fit_score=50, confidence="low",
        strong_matches=[], missing_requirements=[], risks=[], summary="Old.",
    )
    new = JobFitAnalysis(
        eligible=True, fit_score=90, confidence="high",
        strong_matches=["Python"], missing_requirements=[], risks=[], summary="New.",
    )
    await record_analysis(db_session, job, old)
    await record_analysis(db_session, job, new)

    refreshed = await get_job_by_id(db_session, job.id)
    await db_session.refresh(refreshed, attribute_names=["analyses"])
    assert {a.fit_score for a in refreshed.analyses} == {50, 90}
