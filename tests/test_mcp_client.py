"""
Verifies app/sources/mcp/client.py's httpx.AsyncClient lifecycle fix: a
caller-supplied httpx.AsyncClient is never closed by the mcp SDK's own
transport (confirmed against the installed SDK source — see
_mcp_client()'s docstring), so this module must close it itself. Fakes
the SDK's Client/streamable_http_client rather than hitting a real MCP
server — this is a lifecycle test, not an integration test.
"""

from contextlib import asynccontextmanager
from unittest.mock import MagicMock, patch

from app.sources.mcp.client import _auth_headers, call_tool, list_tools


class _FakeHttpxClient:
    """Stands in for httpx.AsyncClient — just tracks whether it was closed."""

    def __init__(self, *args, **kwargs):
        self.closed = False
        self.init_kwargs = kwargs

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc_info):
        self.closed = True


class _FakeMcpClient:
    """Stands in for mcp.Client — records the http_client its transport got."""

    def __init__(self, transport, raise_exceptions=True):
        self.transport = transport

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc_info):
        pass

    async def list_tools(self):
        return MagicMock(tools=["tool-a"])

    async def call_tool(self, tool_name, arguments):
        return {"tool_name": tool_name, "arguments": arguments}


@asynccontextmanager
async def _fake_transport(url, *, http_client=None, terminate_on_close=True):
    yield (None, None)


def test_auth_headers_wraps_bearer_by_default():
    assert _auth_headers("secret", "Authorization") == {"Authorization": "Bearer secret"}


def test_auth_headers_sends_raw_key_for_a_custom_header_name():
    assert _auth_headers("secret", "x-api-key") == {"x-api-key": "secret"}


def test_auth_headers_empty_without_a_key():
    assert _auth_headers(None, "Authorization") == {}


async def test_list_tools_closes_the_httpx_client_it_opens():
    fake_http_client = _FakeHttpxClient()

    with patch("app.sources.mcp.client.httpx.AsyncClient", return_value=fake_http_client), \
         patch("app.sources.mcp.client.streamable_http_client", _fake_transport), \
         patch("app.sources.mcp.client.Client", _FakeMcpClient):
        tools = await list_tools("https://example.com/mcp", "key")

    assert tools == ["tool-a"]
    assert fake_http_client.closed is True


async def test_call_tool_closes_the_httpx_client_it_opens():
    fake_http_client = _FakeHttpxClient()

    with patch("app.sources.mcp.client.httpx.AsyncClient", return_value=fake_http_client), \
         patch("app.sources.mcp.client.streamable_http_client", _fake_transport), \
         patch("app.sources.mcp.client.Client", _FakeMcpClient):
        result = await call_tool("https://example.com/mcp", "key", "search_jobs", {"query": "engineer"})

    assert result == {"tool_name": "search_jobs", "arguments": {"query": "engineer"}}
    assert fake_http_client.closed is True


async def test_httpx_client_is_closed_even_when_the_mcp_call_raises():
    fake_http_client = _FakeHttpxClient()

    class _FailingMcpClient(_FakeMcpClient):
        async def list_tools(self):
            raise RuntimeError("server unreachable")

    with patch("app.sources.mcp.client.httpx.AsyncClient", return_value=fake_http_client), \
         patch("app.sources.mcp.client.streamable_http_client", _fake_transport), \
         patch("app.sources.mcp.client.Client", _FailingMcpClient):
        try:
            await list_tools("https://example.com/mcp", "key")
        except RuntimeError:
            pass

    assert fake_http_client.closed is True
