"""
Configured MCP job-search sources. A source only counts as "configured"
once both its URL and API key are set — explore.py skips any source
that isn't, rather than failing the whole search. See CLAUDE.md rule 2:
no LinkedIn or Naukri MCP connector belongs in this list.
"""

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class McpSource:
    """Configuration for an external MCP job-search server.

    Attributes:
        name: Short identifier for the source (e.g. 'jobo', 'hasdata').
        url: Remote endpoint URL of the streamable HTTP MCP server.
        api_key: Bearer token secret for authentication, or None if unconfigured.
    """
    name: str
    url: str
    api_key: str | None


def configured_sources() -> list[McpSource]:
    """Retrieve all MCP job sources that have both an endpoint URL and API key defined.

    Checks environment variables `JOBO_MCP_URL`, `JOBO_MCP_API_KEY`, `HASDATA_MCP_URL`,
    and `HASDATA_MCP_API_KEY`. Filters out any sources missing credentials.

    Returns:
        list[McpSource]: List of validated, actively configured McpSource objects.
    """
    candidates = [
        McpSource(
            name="jobo",
            url=os.environ.get("JOBO_MCP_URL", "https://jobs-mcp.jobo.world/mcp"),
            api_key=os.environ.get("JOBO_MCP_API_KEY"),
        ),
        McpSource(
            name="hasdata",
            url=os.environ.get("HASDATA_MCP_URL", ""),
            api_key=os.environ.get("HASDATA_MCP_API_KEY"),
        ),
    ]
    return [source for source in candidates if source.api_key and source.url]
