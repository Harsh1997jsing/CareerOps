from unittest.mock import AsyncMock, patch

from app.llm.schemas import ChatResultSummaries, ChatSearchIntent, JobSummaryItem
from app.services.chat_search import (
    extract_intent,
    get_staged_results,
    intent_filters,
    run_search,
    stage_results,
    summarize_results,
)

JOB = {
    "source": "jobo",
    "source_job_id": "j1",
    "company": "Acme",
    "title": "Backend Engineer",
    "location": "Bangalore",
    "url": "https://example.com/apply/j1",
    "description": "Build things",
    "employment_type": "Full-time",
    "posted_at": None,
    "salary_min": None,
    "salary_max": None,
}


def _intent(**overrides):
    defaults = dict(
        query="backend engineer", location=None, experience=None,
        posted_within_days=None, company=None, sources=["explore"],
        ready_to_search=True, clarification_question=None,
    )
    return ChatSearchIntent(**{**defaults, **overrides})


def test_extract_intent_calls_structured_call_with_known_filters():
    with patch("app.services.chat_search.structured_call", return_value=_intent()) as mock_call:
        intent = extract_intent("backend roles in bangalore", {"query": "backend"})

    assert intent.query == "backend engineer"
    prompt = mock_call.call_args.args[0]
    assert "query=backend" in prompt
    assert "backend roles in bangalore" in prompt


def test_intent_filters_only_includes_set_fields():
    intent = _intent(location="Bangalore", experience=None, posted_within_days=7)
    filters = intent_filters(intent)

    assert filters == {"query": "backend engineer", "location": "Bangalore", "posted_within_days": 7}


async def test_run_search_dispatches_to_mcp_explore_with_non_query_filters():
    intent = _intent(location="Bangalore", experience="senior")
    with patch("app.services.chat_search.mcp_explore.search", AsyncMock(return_value=[JOB])) as mock_search:
        results = await run_search(intent)

    assert results == [JOB]
    mock_search.assert_called_once_with("backend engineer", {"location": "Bangalore", "experience": "senior"})


async def test_run_search_dispatches_to_scrape_when_selected():
    intent = _intent(sources=["scrape"], location="Bangalore", experience="senior")
    scrape_job = {**JOB, "source": "jobspy"}
    with patch("app.services.chat_search.jobspy_source.fetch_jobs", return_value=[scrape_job]) as mock_fetch:
        results = await run_search(intent)

    assert results == [scrape_job]
    mock_fetch.assert_called_once_with("backend engineer", location="Bangalore", experience="senior")


async def test_run_search_dispatches_to_targets_when_selected():
    intent = _intent(sources=["targets"], experience="senior")
    target_job = {**JOB, "source": "greenhouse"}
    with patch(
        "app.services.chat_search.targets_source.search_all", AsyncMock(return_value=[target_job])
    ) as mock_search:
        results = await run_search(intent)

    assert results == [target_job]
    mock_search.assert_called_once_with(experience="senior")


async def test_run_search_merges_multiple_sources():
    intent = _intent(sources=["explore", "scrape"])
    explore_job = {**JOB, "source": "jobo"}
    scrape_job = {**JOB, "source_job_id": "j2", "source": "jobspy"}
    with patch("app.services.chat_search.mcp_explore.search", AsyncMock(return_value=[explore_job])), \
         patch("app.services.chat_search.jobspy_source.fetch_jobs", return_value=[scrape_job]):
        results = await run_search(intent)

    assert results == [explore_job, scrape_job]


async def test_run_search_skips_a_failing_source_without_aborting():
    intent = _intent(sources=["explore", "scrape"])
    scrape_job = {**JOB, "source": "jobspy"}
    with patch("app.services.chat_search.mcp_explore.search", AsyncMock(side_effect=RuntimeError("boom"))), \
         patch("app.services.chat_search.jobspy_source.fetch_jobs", return_value=[scrape_job]):
        results = await run_search(intent)

    assert results == [scrape_job]


def test_summarize_results_returns_empty_list_for_no_jobs():
    assert summarize_results([]) == []


def test_summarize_results_maps_summaries_by_index():
    jobs = [JOB, {**JOB, "source_job_id": "j2", "title": "Staff Engineer"}]
    fake_response = ChatResultSummaries(
        summaries=[JobSummaryItem(index=0, summary="Backend role"), JobSummaryItem(index=1, summary="Staff role")]
    )
    with patch("app.services.chat_search.structured_call", return_value=fake_response):
        summaries = summarize_results(jobs)

    assert summaries == ["Backend role", "Staff role"]


def test_summarize_results_defaults_missing_indices_to_empty_string():
    jobs = [JOB, {**JOB, "source_job_id": "j2"}]
    fake_response = ChatResultSummaries(summaries=[JobSummaryItem(index=0, summary="Backend role")])
    with patch("app.services.chat_search.structured_call", return_value=fake_response):
        summaries = summarize_results(jobs)

    assert summaries == ["Backend role", ""]


async def test_stage_results_replaces_prior_staged_rows_for_session(db_session):
    await stage_results(db_session, "sess-1", [JOB])
    second_job = {**JOB, "source_job_id": "j2", "title": "Staff Engineer"}
    staged = await stage_results(db_session, "sess-1", [second_job])

    current = await get_staged_results(db_session, "sess-1")
    assert len(current) == 1
    assert current[0].title == "Staff Engineer"
    assert staged[0].title == "Staff Engineer"


async def test_stage_results_scopes_by_session_id(db_session):
    await stage_results(db_session, "sess-1", [JOB])
    await stage_results(db_session, "sess-2", [{**JOB, "source_job_id": "j2"}])

    sess_1_results = await get_staged_results(db_session, "sess-1")
    sess_2_results = await get_staged_results(db_session, "sess-2")
    assert len(sess_1_results) == 1
    assert len(sess_2_results) == 1


async def test_stage_results_persists_summaries(db_session):
    staged = await stage_results(db_session, "sess-1", [JOB], summaries=["Backend role in Bangalore"])
    assert staged[0].summary == "Backend role in Bangalore"


async def test_stage_results_defaults_summary_to_none_without_summaries(db_session):
    staged = await stage_results(db_session, "sess-1", [JOB])
    assert staged[0].summary is None


