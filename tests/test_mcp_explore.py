from unittest.mock import AsyncMock, patch

from mcp.types import CallToolResult, Tool

from app.sources.mcp.explore import (
    _build_search_arguments,
    _extract_results,
    get_all_capabilities,
    normalize_result,
    search,
    search_source,
)
from app.sources.mcp.registry import McpSource

JOBO = McpSource(name="jobo", url="https://jobs-mcp.jobo.world/mcp", api_key="jobo-key")
HASDATA = McpSource(name="hasdata", url="https://hasdata.example/mcp", api_key="hasdata-key")

SEARCH_TOOL = Tool(
    name="search_jobs",
    description="Search job postings",
    input_schema={
        "type": "object",
        "properties": {
            "query": {"type": "string"},
            "location": {"type": "string"},
            "company": {"type": "string"},
        },
    },
)

RAW_RESULT = {
    "id": "j1",
    "title": "Backend Engineer",
    "company": "Acme",
    "location": "Bengaluru, Karnataka",
    "apply_url": "https://example.com/apply/j1",
    "description": "<p>Build things</p>",
    "job_type": "fulltime",
    "salary_min": 1000000,
    "salary_max": 1500000,
}


def test_normalize_result_maps_fields():
    job = normalize_result("jobo", RAW_RESULT)

    assert job["source"] == "jobo"
    assert job["source_job_id"] == "j1"
    assert job["company"] == "Acme"
    assert job["title"] == "Backend Engineer"
    assert job["location"] == "Bangalore"
    assert job["url"] == "https://example.com/apply/j1"
    assert job["description"] == "Build things"
    assert job["employment_type"] == "Full-time"
    assert job["salary_min"] == 1000000
    assert len(job["description_hash"]) == 64


def test_extract_results_prefers_structured_content_list():
    result = CallToolResult(content=[], structured_content=[RAW_RESULT])
    assert _extract_results(result) == [RAW_RESULT]


def test_extract_results_unwraps_structured_content_dict():
    result = CallToolResult(content=[], structured_content={"results": [RAW_RESULT]})
    assert _extract_results(result) == [RAW_RESULT]


def test_extract_results_falls_back_to_text_json():
    result = CallToolResult(content=[{"type": "text", "text": '{"jobs": [{"title": "x"}]}'}])
    assert _extract_results(result) == [{"title": "x"}]


def test_extract_results_returns_empty_for_unparseable_text():
    result = CallToolResult(content=[{"type": "text", "text": "not json"}])
    assert _extract_results(result) == []


def test_build_search_arguments_maps_query_and_known_filters():
    arguments = _build_search_arguments(
        SEARCH_TOOL, "backend engineer", {"location": "Bangalore", "skills": ["python"]}
    )
    assert arguments == {"query": "backend engineer", "location": "Bangalore"}


async def test_search_source_calls_detected_tool_with_mapped_arguments():
    call_result = CallToolResult(content=[], structured_content=[RAW_RESULT])
    with patch("app.sources.mcp.explore.list_tools", AsyncMock(return_value=[SEARCH_TOOL])), \
         patch("app.sources.mcp.explore.call_tool", AsyncMock(return_value=call_result)) as mock_call:
        jobs = await search_source(JOBO, "backend engineer", {"location": "Bangalore"})

    assert len(jobs) == 1
    assert jobs[0]["source"] == "jobo"
    mock_call.assert_called_once_with(
        JOBO.url, JOBO.api_key, "search_jobs", {"query": "backend engineer", "location": "Bangalore"}
    )


async def test_search_source_skips_when_no_search_tool_found():
    with patch("app.sources.mcp.explore.list_tools", AsyncMock(return_value=[Tool(name="ping", input_schema={})])), \
         patch("app.sources.mcp.explore.call_tool", AsyncMock()) as mock_call:
        jobs = await search_source(JOBO, "backend engineer", {})

    assert jobs == []
    mock_call.assert_not_called()


async def test_search_source_returns_empty_on_tool_error():
    call_result = CallToolResult(content=[{"type": "text", "text": "boom"}], is_error=True)
    with patch("app.sources.mcp.explore.list_tools", AsyncMock(return_value=[SEARCH_TOOL])), \
         patch("app.sources.mcp.explore.call_tool", AsyncMock(return_value=call_result)):
        jobs = await search_source(JOBO, "backend engineer", {})

    assert jobs == []


async def test_search_fans_out_across_configured_sources_and_skips_failures():
    call_result = CallToolResult(content=[], structured_content=[RAW_RESULT])

    async def fake_search_source(source, query, filters):
        if source.name == "jobo":
            return [normalize_result("jobo", RAW_RESULT)]
        raise RuntimeError("hasdata is down")

    with patch("app.sources.mcp.explore.configured_sources", return_value=[JOBO, HASDATA]), \
         patch("app.sources.mcp.explore.search_source", side_effect=fake_search_source):
        jobs = await search("backend engineer")

    assert len(jobs) == 1
    assert jobs[0]["source"] == "jobo"


async def test_search_returns_empty_when_no_sources_configured():
    with patch("app.sources.mcp.explore.configured_sources", return_value=[]):
        jobs = await search("backend engineer")
    assert jobs == []


async def test_get_all_capabilities_skips_a_source_that_errors():
    async def fake_get_capability_matrix(source):
        if source.name == "jobo":
            raise RuntimeError("unreachable")
        from app.sources.mcp.capabilities import build_capability_matrix
        return build_capability_matrix([SEARCH_TOOL])

    with patch("app.sources.mcp.explore.configured_sources", return_value=[JOBO, HASDATA]), \
         patch("app.sources.mcp.explore.get_capability_matrix", side_effect=fake_get_capability_matrix):
        matrix = await get_all_capabilities()

    assert "jobo" not in matrix
    assert "hasdata" in matrix
    assert matrix["hasdata"].supports("search")
