"""
Thin wrapper around the `mcp` SDK's high-level Client for talking to a
remote MCP job-search server over Streamable HTTP with a bearer token.
Nothing else in this package should import the SDK directly — mirrors
how app/llm/anthropic_client.py is the sole place that touches the
Anthropic SDK.
"""

import httpx
from mcp import Client
from mcp.client.streamable_http import streamable_http_client
from mcp.types import CallToolResult, Tool


def _make_client(url: str, api_key: str | None, auth_header: str = "Authorization") -> Client:
    """Initialize an MCP Client using streamable HTTP transport.

    Args:
        url: Remote endpoint URL of the MCP server.
        api_key: Optional secret for server authentication.
        auth_header: Header to send the key in. "Authorization" wraps it as
            "Bearer <key>"; anything else sends the raw key as that header
            verbatim — see McpSource.auth_header for why this varies per
            source instead of always being Bearer.

    Returns:
        Client: Instantiated high-level MCP client.
    """
    headers: dict[str, str] = {}
    if api_key:
        if auth_header.lower() == "authorization":
            headers["Authorization"] = f"Bearer {api_key}"
        else:
            headers[auth_header] = api_key
    http_client = httpx.AsyncClient(headers=headers, timeout=30.0)
    transport = streamable_http_client(url, http_client=http_client)
    return Client(transport, raise_exceptions=True)


async def list_tools(url: str, api_key: str | None, auth_header: str = "Authorization") -> list[Tool]:
    """Query an MCP server for its registered list of tools.

    Args:
        url: MCP server endpoint URL.
        api_key: Optional token for authentication.
        auth_header: Header to send the key in — see _make_client.

    Returns:
        list[Tool]: List of tool definitions advertised by the server.
    """
    async with _make_client(url, api_key, auth_header) as client:
        result = await client.list_tools()
        return result.tools


async def call_tool(
    url: str, api_key: str | None, tool_name: str, arguments: dict, auth_header: str = "Authorization"
) -> CallToolResult:
    """Invoke a named tool on a remote MCP server with specified arguments.

    Args:
        url: MCP server endpoint URL.
        api_key: Optional authentication token.
        tool_name: Name of the remote tool to execute.
        arguments: Dictionary of arguments conforming to the tool's input schema.
        auth_header: Header to send the key in — see _make_client.

    Returns:
        CallToolResult: Structured or textual output returned by the MCP tool invocation.
    """
    async with _make_client(url, api_key, auth_header) as client:
        return await client.call_tool(tool_name, arguments)
