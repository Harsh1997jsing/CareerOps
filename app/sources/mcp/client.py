"""
Thin wrapper around the `mcp` SDK's high-level Client for talking to a
remote MCP job-search server over Streamable HTTP with a bearer token.
Nothing else in this package should import the SDK directly — mirrors
how app/llm/anthropic_client.py is the sole place that touches the
Anthropic SDK.
"""

from contextlib import asynccontextmanager
from typing import AsyncIterator

import httpx
from mcp import Client
from mcp.client.streamable_http import streamable_http_client
from mcp.types import CallToolResult, Tool


def _auth_headers(api_key: str | None, auth_header: str) -> dict[str, str]:
    """Build the auth header(s) for an MCP request.

    Args:
        api_key: Optional secret for server authentication.
        auth_header: Header to send the key in. "Authorization" wraps it as
            "Bearer <key>"; anything else sends the raw key as that header
            verbatim — see McpSource.auth_header for why this varies per
            source instead of always being Bearer.

    Returns:
        dict[str, str]: Header(s) to attach to the request, empty if no key.
    """
    if not api_key:
        return {}
    if auth_header.lower() == "authorization":
        return {"Authorization": f"Bearer {api_key}"}
    return {auth_header: api_key}


@asynccontextmanager
async def _mcp_client(url: str, api_key: str | None, auth_header: str = "Authorization") -> AsyncIterator[Client]:
    """Open an MCP Client over streamable HTTP, closing every resource it opens.

    `streamable_http_client(url, http_client=...)`'s own docstring (and the
    installed SDK's `client_provided` check) is explicit that a
    caller-supplied `httpx.AsyncClient` is left for the *caller* to close —
    it's never registered on the transport's own exit stack. The previous
    version of this module handed one in without ever closing it, leaking
    one `httpx.AsyncClient` (and its connection pool) per `list_tools()`/
    `call_tool()` call — confirmed against the installed `mcp` SDK source.
    Owning the `httpx.AsyncClient` in this function's own `async with`,
    nested outside the `Client`'s, guarantees it's closed after the
    `Client` (and the transport session it drives) has finished using it.

    Args:
        url: Remote endpoint URL of the MCP server.
        api_key: Optional secret for server authentication.
        auth_header: Header to send the key in — see _auth_headers().

    Yields:
        Client: An entered, ready-to-use high-level MCP client.
    """
    async with httpx.AsyncClient(headers=_auth_headers(api_key, auth_header), timeout=30.0) as http_client:
        transport = streamable_http_client(url, http_client=http_client)
        async with Client(transport, raise_exceptions=True) as client:
            yield client


async def list_tools(url: str, api_key: str | None, auth_header: str = "Authorization") -> list[Tool]:
    """Query an MCP server for its registered list of tools.

    Args:
        url: MCP server endpoint URL.
        api_key: Optional token for authentication.
        auth_header: Header to send the key in — see _auth_headers().

    Returns:
        list[Tool]: List of tool definitions advertised by the server.
    """
    async with _mcp_client(url, api_key, auth_header) as client:
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
        auth_header: Header to send the key in — see _auth_headers().

    Returns:
        CallToolResult: Structured or textual output returned by the MCP tool invocation.
    """
    async with _mcp_client(url, api_key, auth_header) as client:
        return await client.call_tool(tool_name, arguments)
