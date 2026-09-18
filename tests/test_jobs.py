from datetime import datetime

from app.models import GeneratedDocument, JobAnalysis
from app.services.jobs import get_job, list_generated_documents, list_jobs
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
