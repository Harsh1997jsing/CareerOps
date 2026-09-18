"""
Configured MCP job-search sources. A source only counts as "configured"
once both its URL and API key are set — explore.py skips any source
that isn't, rather than failing the whole search. See CLAUDE.md rule 2:
no LinkedIn or Naukri MCP connector belongs in this list.
"""

from dataclasses import dataclass

from app.core.config import get_settings


@dataclass(frozen=True)
class McpSource:
    """Configuration for an external MCP job-search server.

    Attributes:
        name: Short identifier for the source (e.g. 'jobo', 'hasdata').
        url: Remote endpoint URL of the streamable HTTP MCP server.
        api_key: Secret for authentication, or None if unconfigured.
        auth_header: Header name the key is sent in. "Authorization" sends
            it as "Bearer <key>"; any other name sends the raw key as that
            header's value verbatim (e.g. HasData's "x-api-key" — confirmed
            by hand against the live server: its gateway accepts an
            Authorization: Bearer header for list_tools/initialize, but a
            real tools/call only succeeds with x-api-key; Bearer gets a 401
            from HasData's own downstream API at execution time).
    """
    name: str
    url: str
    api_key: str | None
    auth_header: str = "Authorization"


def configured_sources() -> list[McpSource]:
    """Retrieve all MCP job sources that have both an endpoint URL and API key defined.

    Checks settings for `jobo_mcp_url`, `jobo_mcp_api_key`, `hasdata_mcp_url`,
    and `hasdata_mcp_api_key`. Filters out any sources missing credentials.

    Returns:
        list[McpSource]: List of validated, actively configured McpSource objects.
    """
    settings = get_settings()
    candidates = [
        McpSource(
            name="jobo",
            url=settings.jobo_mcp_url,
            api_key=settings.jobo_mcp_api_key or None,
        ),
        McpSource(
            name="hasdata",
            url=settings.hasdata_mcp_url,
            api_key=settings.hasdata_mcp_api_key or None,
            auth_header="x-api-key",
        ),
    ]
    return [source for source in candidates if source.api_key and source.url]
