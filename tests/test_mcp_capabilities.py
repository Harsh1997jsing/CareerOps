from mcp.types import Tool

from app.sources.mcp.capabilities import build_capability_matrix


def _tool(name, description="", properties=None):
    return Tool(
        name=name,
        description=description,
        input_schema={"type": "object", "properties": properties or {}},
    )


def test_detects_search_tool_by_name():
    matrix = build_capability_matrix([_tool("search_jobs"), _tool("get_job_details")])

    assert matrix.supports("search")
    assert matrix.search_tool.name == "search_jobs"
    assert matrix.supports("details")
    assert matrix.details_tool.name == "get_job_details"


def test_detects_filters_from_schema_properties():
    tool = _tool(
        "find_jobs",
        properties={"location": {"type": "string"}, "company": {"type": "string"}},
    )
    matrix = build_capability_matrix([tool])

    assert matrix.supports("location_filter")
    assert matrix.supports("company_filter")
    assert not matrix.supports("skill_filter")


def test_missing_capability_reports_false_not_error():
    matrix = build_capability_matrix([_tool("ping")])

    assert matrix.supports("search") is False
    assert matrix.search_tool is None
    assert matrix.supports("apply_url") is False


def test_empty_tool_list_yields_all_false():
    matrix = build_capability_matrix([])

    assert all(value is False for value in matrix.flags.values())
    assert matrix.search_tool is None
    assert matrix.details_tool is None
    assert matrix.required_filters == []


def test_required_filters_maps_schema_required_props_to_filter_keys():
    tool = _tool(
        "find_jobs",
        properties={"query": {"type": "string"}, "location": {"type": "string"}},
    )
    tool.input_schema["required"] = ["query", "location"]

    matrix = build_capability_matrix([tool])

    # "query" has no matching filter key (it's the free-text search term,
    # not a filter) so only "location" should surface.
    assert matrix.required_filters == ["location"]


def test_required_filters_empty_when_schema_has_no_required_array():
    tool = _tool("find_jobs", properties={"location": {"type": "string"}})
    matrix = build_capability_matrix([tool])

    assert matrix.required_filters == []
