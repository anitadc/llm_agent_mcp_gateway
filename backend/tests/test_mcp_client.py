import os
import uuid

import httpx
import pytest
import respx

from app.core.config import Settings
from app.core.exceptions import ProviderError
from app.db.models.mcp_server import McpServer
from app.services.mcp.mcp_client import MCP_SESSION_HEADER, McpClient


def _settings() -> Settings:
    return Settings(
        database_url="postgresql+asyncpg://test:test@localhost/test",
        valkey_url="redis://localhost:6379/1",
        keycloak_base_url="http://localhost:8080",
        keycloak_realm="tcsaigateway",
        keycloak_client_id="tcsaigateway-frontend",
        keycloak_audience="tcsaigateway-backend",
        guardrails_base_url="http://localhost:9000",
        api_key_secret_pepper="pepper",
    )


def _server(**overrides) -> McpServer:
    defaults = dict(
        id=uuid.uuid4(),
        name="threat-intel",
        base_url="http://mcp.test/mcp",
        auth_config={},
        protocol_version=None,
    )
    defaults.update(overrides)
    return McpServer(**defaults)


@pytest.mark.asyncio
@respx.mock
async def test_initialize_captures_session_id_and_protocol_version() -> None:
    respx.post("http://mcp.test/mcp").mock(
        return_value=httpx.Response(
            200,
            headers={MCP_SESSION_HEADER: "server-session-abc"},
            json={"jsonrpc": "2.0", "id": "1", "result": {"protocolVersion": "2025-06-18"}},
        )
    )
    client = McpClient(_settings())

    result = await client.initialize(_server())

    assert result.session_id == "server-session-abc"
    assert result.payload["result"]["protocolVersion"] == "2025-06-18"


@pytest.mark.asyncio
@respx.mock
async def test_list_tools_returns_tool_list() -> None:
    respx.post("http://mcp.test/mcp").mock(
        return_value=httpx.Response(
            200,
            json={
                "jsonrpc": "2.0",
                "id": "1",
                "result": {"tools": [{"name": "get_top_threats", "description": "desc", "inputSchema": {}}]},
            },
        )
    )
    client = McpClient(_settings())

    tools = await client.list_tools(_server(), session_id="server-session-abc")

    assert tools[0]["name"] == "get_top_threats"


@pytest.mark.asyncio
@respx.mock
async def test_list_tools_raises_provider_error_on_jsonrpc_error() -> None:
    respx.post("http://mcp.test/mcp").mock(
        return_value=httpx.Response(
            200, json={"jsonrpc": "2.0", "id": "1", "error": {"code": -32000, "message": "boom"}}
        )
    )
    client = McpClient(_settings())

    with pytest.raises(ProviderError):
        await client.list_tools(_server(), session_id=None)


@pytest.mark.asyncio
@respx.mock
async def test_call_tool_forwards_session_header_and_bearer_token() -> None:
    os.environ["MCP_TEST_TOKEN"] = "s3cr3t"
    try:
        route = respx.post("http://mcp.test/mcp").mock(
            return_value=httpx.Response(
                200, json={"jsonrpc": "2.0", "id": "req-1", "result": {"content": [{"type": "text", "text": "ok"}]}}
            )
        )
        client = McpClient(_settings())
        server = _server(auth_config={"type": "bearer", "credential_ref": "MCP_TEST_TOKEN"})

        result = await client.call_tool(server, "server-session-abc", "req-1", "get_top_threats", {"region": "us"})

        assert result.payload["result"]["content"][0]["text"] == "ok"
        sent = route.calls[0].request
        assert sent.headers[MCP_SESSION_HEADER] == "server-session-abc"
        assert sent.headers["Authorization"] == "Bearer s3cr3t"
    finally:
        del os.environ["MCP_TEST_TOKEN"]


@pytest.mark.asyncio
@respx.mock
async def test_call_tool_forwards_custom_api_key_header() -> None:
    os.environ["MCP_TEST_API_KEY"] = "k3y"
    try:
        route = respx.post("http://mcp.test/mcp").mock(
            return_value=httpx.Response(200, json={"jsonrpc": "2.0", "id": "req-1", "result": {}})
        )
        client = McpClient(_settings())
        server = _server(
            auth_config={"type": "api_key", "credential_ref": "MCP_TEST_API_KEY", "header_name": "X-Api-Key"}
        )

        await client.call_tool(server, None, "req-1", "get_top_threats", {})

        assert route.calls[0].request.headers["X-Api-Key"] == "k3y"
    finally:
        del os.environ["MCP_TEST_API_KEY"]


@pytest.mark.asyncio
@respx.mock
async def test_call_tool_does_not_retry_on_transport_error() -> None:
    route = respx.post("http://mcp.test/mcp").mock(side_effect=httpx.ConnectError("boom"))
    client = McpClient(_settings())

    with pytest.raises(ProviderError):
        await client.call_tool(_server(), None, "req-1", "get_top_threats", {})

    assert route.call_count == 1


@pytest.mark.asyncio
@respx.mock
async def test_initialize_retries_transient_transport_error() -> None:
    route = respx.post("http://mcp.test/mcp")
    route.side_effect = [
        httpx.ConnectError("boom"),
        httpx.Response(200, headers={MCP_SESSION_HEADER: "s1"}, json={"jsonrpc": "2.0", "id": "1", "result": {}}),
    ]
    client = McpClient(_settings())

    result = await client.initialize(_server())

    assert result.session_id == "s1"
    assert route.call_count == 2
