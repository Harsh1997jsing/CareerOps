"""
Builds a capability matrix for a connected MCP source from its actual
`list_tools()` response — never assumed. Different servers name their
tools and parameters differently, so matching is heuristic (keyword
search over tool name, description, and input-schema property names).
This is the "capability detection" step CLAUDE.md/the Explore spec calls
for: don't fail the whole search when a source lacks a capability, just
mark it unsupported and let explore.py work around it.
"""

from dataclasses import dataclass, field

from mcp.types import Tool

CAPABILITY_KEYWORDS: dict[str, tuple[str, ...]] = {
    "search": ("search", "find_jobs", "job_search", "query_jobs", "list_jobs"),
    "filters": ("filter",),
    "company_filter": ("company", "employer"),
    "location_filter": ("location", "city", "region"),
    "experience_filter": ("experience", "seniority", "years"),
    "date_filter": ("posted", "date", "recent", "hours_old"),
    "remote_filter": ("remote", "hybrid", "onsite", "work_model", "worktype"),
    "employment_type_filter": ("employment_type", "job_type", "commitment"),
    "skill_filter": ("skill", "tech", "stack"),
    "salary_filter": ("salary", "compensation", "pay"),
    "details": ("detail", "get_job", "job_info", "job_detail"),
    "apply_url": ("apply", "url", "link", "hosted_url"),
}

# Canonical filter key -> candidate schema property names a search tool
# might call it, in priority order. Shared with explore.py's
# _build_search_arguments() (which maps a filter dict onto a tool's actual
# schema) so the same candidate list is used both to build arguments and
# to work out, here, which of a tool's *required* properties correspond to
# a filter the caller needs to supply.
FILTER_PARAM_CANDIDATES: dict[str, tuple[str, ...]] = {
    "location": ("location", "city", "region"),
    "company": ("company", "employer"),
    "employment_type": ("employment_type", "job_type", "commitment"),
    "remote": ("remote", "is_remote", "work_model"),
    "experience": ("experience", "seniority", "years"),
    "skills": ("skills", "skill"),
    "posted_within_days": ("hours_old", "posted_within_days", "date_posted"),
}

_PROPERTY_TO_FILTER_KEY: dict[str, str] = {
    prop: filter_key for filter_key, candidates in FILTER_PARAM_CANDIDATES.items() for prop in candidates
}


@dataclass
class CapabilityMatrix:
    """Discovered feature flags and designated tools for an MCP server.

    Attributes:
        flags: Dictionary mapping capability name strings to support booleans.
        search_tool: The discovered Tool object to use for querying jobs, if supported.
        details_tool: The discovered Tool object to fetch job details, if supported.
        required_filters: Canonical filter keys (see FILTER_PARAM_CANDIDATES)
            that search_tool's own JSON Schema marks as required — a search
            omitting one of these is guaranteed to fail against this source,
            not just miss out on narrowing.
    """
    flags: dict[str, bool]
    search_tool: Tool | None
    details_tool: Tool | None
    required_filters: list[str] = field(default_factory=list)

    def supports(self, capability: str) -> bool:
        """Check whether the MCP server supports a specific capability.

        Args:
            capability: Capability key (e.g. 'search', 'location_filter', 'remote_filter').

        Returns:
            bool: True if supported; False otherwise.
        """
        return self.flags.get(capability, False)


def _tool_text(tool: Tool) -> str:
    """Concatenate a tool's name, description, and input property keys into lowercase text.

    Args:
        tool: An MCP Tool object.

    Returns:
        str: Combined searchable lowercase text.
    """
    schema_props = " ".join((tool.input_schema or {}).get("properties", {}).keys())
    return " ".join(filter(None, [tool.name, tool.description, schema_props])).lower()


def _required_filter_keys(tool: Tool | None) -> list[str]:
    """Map a tool's JSON Schema `required` properties onto canonical filter keys.

    A tool's `input_schema["required"]` (standard JSON Schema) names raw
    parameter properties (e.g. "location"), not the caller-facing filter
    vocabulary this app searches with — this translates via
    FILTER_PARAM_CANDIDATES the same way _build_search_arguments() maps the
    other direction. A required property with no matching filter key
    (e.g. the tool's own "query" param) is silently dropped rather than
    surfaced as an unsatisfiable filter.

    Args:
        tool: The source's designated search tool, or None if it has none.

    Returns:
        list[str]: Canonical filter keys the caller must supply, sorted.
    """
    if tool is None:
        return []
    required_props = (tool.input_schema or {}).get("required") or []
    keys = {_PROPERTY_TO_FILTER_KEY[prop] for prop in required_props if prop in _PROPERTY_TO_FILTER_KEY}
    return sorted(keys)


def _matches(text: str, keywords: tuple[str, ...]) -> bool:
    """Check if any keyword in a tuple appears as a substring in the given text.

    Args:
        text: Lowercase search string.
        keywords: Tuple of keyword substrings.

    Returns:
        bool: True if at least one keyword matches.
    """
    return any(keyword in text for keyword in keywords)


def build_capability_matrix(tools: list[Tool]) -> CapabilityMatrix:
    """Analyze an MCP server's tools and build a CapabilityMatrix.

    Performs heuristic keyword analysis over tool names, descriptions, and input schema
    properties to detect support for search, filtering, and detail endpoints.

    Args:
        tools: List of Tool descriptions returned by the MCP server.

    Returns:
        CapabilityMatrix: Capability flags and designated search/detail tools.
    """
    tool_texts = [(tool, _tool_text(tool)) for tool in tools]

    # A dedicated job-search MCP server (Jobo) only exposes job tools, so
    # every tool is fair game. A general-purpose scraping platform (HasData:
    # 63 tools spanning Airbnb, Zillow, etc.) is not — matching "search"
    # against its full tool list picks up e.g. an Airbnb listing tool
    # (its description also says "Searches Airbnb for..."), which then gets
    # called with job-search arguments and fails. Restrict to tools whose
    # own text mentions "job" first; only fall back to the unfiltered set
    # if that leaves nothing (a Jobo-like server with no literal "job" in
    # its tool text would otherwise report zero capabilities).
    job_tool_texts = [(tool, text) for tool, text in tool_texts if "job" in text]
    candidate_texts = job_tool_texts or tool_texts

    flags = {
        capability: any(_matches(text, keywords) for _, text in candidate_texts)
        for capability, keywords in CAPABILITY_KEYWORDS.items()
    }

    search_tool = next(
        (tool for tool, text in candidate_texts if _matches(text, CAPABILITY_KEYWORDS["search"])),
        None,
    )
    details_tool = next(
        (tool for tool, text in candidate_texts if _matches(text, CAPABILITY_KEYWORDS["details"])),
        None,
    )

    return CapabilityMatrix(
        flags=flags,
        search_tool=search_tool,
        details_tool=details_tool,
        required_filters=_required_filter_keys(search_tool),
    )
