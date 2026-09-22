from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import patch

from sqlalchemy import select, update

from app.llm.schemas import JobFitAnalysis
from app.models import GeneratedDocument, Job, JobAnalysis
from app.services.jobs import (
    DEFAULT_JOB_STATUS,
    REJECTED_JOB_STATUS,
    analyze_job,
    get_job,
    get_job_by_id,
    hard_filter_job,
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


async def test_list_jobs_treats_a_literal_percent_in_q_as_literal_not_a_wildcard(db_session):
    # Full code audit finding: q wasn't escaped before .ilike(f"%{q}%"),
    # so searching q="50%" was silently read as "contains 50" (the
    # trailing "%" absorbed as a no-op wildcard) rather than requiring a
    # literal "%" after the 50 — job_id=2 ("50 years", no percent sign)
    # would wrongly match too before this fix.
    await make_job(db_session, job_id=1, description="Bonus: up to 50% equity")
    await make_job(db_session, job_id=2, description="Minimum 50 years combined team experience")

    jobs = await list_jobs(db_session, q="50%")

    assert [j.job_id for j in jobs] == [1]


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


def _write_constraints(tmp_path):
    path = tmp_path / "constraints.yaml"
    path.write_text(
        "allowed_locations: [Remote, Bangalore]\n"
        "employment_types: [Full-time]\n"
        "minimum_experience_years: 0\n"
        "acceptable_experience_gap_years: 1\n"
        "exclude_keywords: [unpaid internship]\n"
    )
    return str(path)


async def test_hard_filter_job_passes_within_constraints(db_session, tmp_path):
    job = await make_job(db_session, location="Bangalore", employment_type="Full-time")
    result = await hard_filter_job(db_session, job, _write_constraints(tmp_path))
    assert result.passed


async def test_hard_filter_job_fails_disallowed_location(db_session, tmp_path):
    job = await make_job(db_session, location="Mumbai", employment_type="Full-time")
    result = await hard_filter_job(db_session, job, _write_constraints(tmp_path))
    assert not result.passed
    assert any("location" in r for r in result.reasons)


async def test_hard_filter_job_fails_excluded_keyword(db_session, tmp_path):
    job = await make_job(
        db_session, location="Remote", employment_type="Full-time",
        description="This is an unpaid internship opportunity.",
    )
    result = await hard_filter_job(db_session, job, _write_constraints(tmp_path))
    assert not result.passed
    assert any("excluded keyword" in r for r in result.reasons)


async def test_hard_filter_job_fails_company_cooldown(db_session, tmp_path):
    from datetime import datetime, timedelta

    from app.models import CompanyApplicationHistory

    path = tmp_path / "constraints.yaml"
    path.write_text(
        "allowed_locations: [Remote]\n"
        "employment_types: [Full-time]\n"
        "minimum_experience_years: 0\n"
        "acceptable_experience_gap_years: 1\n"
        "exclude_keywords: []\n"
        "company_cooldown_days: 30\n"
    )
    job = await make_job(db_session, location="Remote", employment_type="Full-time", company="Acme")
    db_session.add(CompanyApplicationHistory(company="Acme", applied_at=datetime.now() - timedelta(days=5)))
    await db_session.commit()

    result = await hard_filter_job(db_session, job, str(path))

    assert not result.passed
    assert any("Acme" in r for r in result.reasons)


async def test_hard_filter_job_passes_company_cooldown_when_no_history(db_session, tmp_path):
    path = tmp_path / "constraints.yaml"
    path.write_text(
        "allowed_locations: [Remote]\n"
        "employment_types: [Full-time]\n"
        "minimum_experience_years: 0\n"
        "acceptable_experience_gap_years: 1\n"
        "exclude_keywords: []\n"
        "company_cooldown_days: 30\n"
    )
    job = await make_job(db_session, location="Remote", employment_type="Full-time", company="NewCo")

    result = await hard_filter_job(db_session, job, str(path))

    assert result.passed


def _fake_settings(tmp_path):
    # analyze_job() only ever reads .constraints_path/.skills_path/
    # .evidence_path off whatever it's handed — a real Settings instance
    # isn't needed, and score_job() itself is mocked below so
    # skills_path/evidence_path are never actually opened.
    return SimpleNamespace(
        constraints_path=_write_constraints(tmp_path), skills_path="unused", evidence_path="unused",
    )


async def test_analyze_job_short_circuits_on_failed_hard_filter(db_session, tmp_path):
    # Same pipeline order CLAUDE.md requires at the route level: a job
    # outside allowed_locations never reaches the LLM scorer at all.
    job = await make_job(db_session, location="Mumbai", employment_type="Full-time", status="DISCOVERED")

    with patch("app.services.jobs.job_scorer.score_job") as mock_score:
        updated = await analyze_job(db_session, job, _fake_settings(tmp_path))

    mock_score.assert_not_called()
    assert updated.status == "REJECT"


async def test_analyze_job_scores_records_and_sets_status_when_hard_filter_passes(db_session, tmp_path):
    job = await make_job(db_session, location="Bangalore", employment_type="Full-time", status="DISCOVERED")
    analysis = JobFitAnalysis(
        eligible=True, fit_score=90, confidence="high",
        strong_matches=["Python"], missing_requirements=[], risks=[], summary="Great fit.",
    )

    with patch("app.services.jobs.job_scorer.score_job", return_value=analysis) as mock_score:
        updated = await analyze_job(db_session, job, _fake_settings(tmp_path))

    mock_score.assert_called_once()
    assert updated.status == "READY_FOR_REVIEW"
    persisted = (await db_session.scalars(select(JobAnalysis).where(JobAnalysis.job_id == job.id))).one()
    assert persisted.fit_score == 90


async def test_analyze_job_skips_scoring_when_a_concurrent_analyze_already_won(tmp_path):
    # Simulates the auto-analyze-on-save background task racing a
    # foreground /jobs/{id}/analyze click on the same freshly-saved job —
    # two independent sessions on the same engine, exactly like two real
    # concurrent requests each getting their own session from get_db().
    # Reusing db_session's single session for both the "concurrent" update
    # and analyze_job() itself would be a false pass: SQLAlchemy's
    # ORM-enabled UPDATE auto-synchronizes any already-loaded object in
    # that *same* session's identity map, silently updating `job.status`
    # in-memory too — which two genuinely separate sessions never do for
    # each other, and is exactly the gap this guard exists to cover.
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    from app.models import Base

    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    session_factory = async_sessionmaker(bind=engine, expire_on_commit=False)

    try:
        async with session_factory() as session_a:
            job = await make_job(session_a, location="Bangalore", employment_type="Full-time", status="DISCOVERED")

            # The "other" concurrent request, on its own independent
            # session — session_a's identity map (and job.status in
            # memory) stays exactly as it was, same as two real requests.
            async with session_factory() as session_b:
                await session_b.execute(update(Job).where(Job.id == job.id).values(status="REVIEW_REQUIRED"))
                await session_b.commit()

            with patch("app.services.jobs.job_scorer.score_job") as mock_score:
                result = await analyze_job(session_a, job, _fake_settings(tmp_path))
    finally:
        await engine.dispose()

    mock_score.assert_not_called()
    assert result is job


async def test_analyze_job_reanalyze_of_an_already_scored_job_is_not_blocked_by_the_guard(db_session, tmp_path):
    # The race guard above must only ever apply to a job that was still
    # DISCOVERED when analyze_job() was called — an intentional re-analyze
    # of an already-scored job (any other status) always runs, per
    # record_analysis()'s documented "adds a new row" behavior.
    job = await make_job(db_session, location="Bangalore", employment_type="Full-time", status="REVIEW_REQUIRED")
    analysis = JobFitAnalysis(
        eligible=True, fit_score=88, confidence="high",
        strong_matches=[], missing_requirements=[], risks=[], summary="Re-scored.",
    )

    with patch("app.services.jobs.job_scorer.score_job", return_value=analysis) as mock_score:
        updated = await analyze_job(db_session, job, _fake_settings(tmp_path))

    mock_score.assert_called_once()
    assert updated.status == "READY_FOR_REVIEW"
