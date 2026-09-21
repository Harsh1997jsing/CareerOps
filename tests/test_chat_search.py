from unittest.mock import AsyncMock, patch

from app.llm.schemas import ChatSearchIntent
from app.services.chat_search import (
    extract_intent,
    get_staged_results,
    intent_filters,
    run_search,
    stage_results,
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
        posted_within_days=None, company=None, ready_to_search=True,
        clarification_question=None,
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


