"""
Builds a capability matrix for a connected MCP source from its actual
`list_tools()` response — never assumed. Different servers name their
tools and parameters differently, so matching is heuristic (keyword
search over tool name, description, and input-schema property names).
This is the "capability detection" step CLAUDE.md/the Explore spec calls
for: don't fail the whole search when a source lacks a capability, just
mark it unsupported and let explore.py work around it.
"""

from dataclasses import dataclass

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


@dataclass
class CapabilityMatrix:
    """Discovered feature flags and designated tools for an MCP server.

    Attributes:
        flags: Dictionary mapping capability name strings to support booleans.
        search_tool: The discovered Tool object to use for querying jobs, if supported.
        details_tool: The discovered Tool object to fetch job details, if supported.
    """
    flags: dict[str, bool]
    search_tool: Tool | None
    details_tool: Tool | None

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

    flags = {
        capability: any(_matches(text, keywords) for _, text in tool_texts)
        for capability, keywords in CAPABILITY_KEYWORDS.items()
    }

    search_tool = next(
        (tool for tool, text in tool_texts if _matches(text, CAPABILITY_KEYWORDS["search"])),
        None,
    )
    details_tool = next(
        (tool for tool, text in tool_texts if _matches(text, CAPABILITY_KEYWORDS["details"])),
        None,
    )

    return CapabilityMatrix(flags=flags, search_tool=search_tool, details_tool=details_tool)
