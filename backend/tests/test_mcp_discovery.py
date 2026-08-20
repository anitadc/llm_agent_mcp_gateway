import httpx
import pytest
import respx
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.db.models.enums import McpHealthStatus, McpSyncStatus
from app.db.models.mcp_server import McpServer
from app.repositories.mcp_server_repo import McpServerRepo
from app.repositories.mcp_tool_repo import McpToolRepo
from app.services.mcp.discovery_service import DiscoveryService
from app.services.mcp.health_checker import HealthChecker
from app.services.mcp.mcp_client import MCP_SESSION_HEADER, McpClient


def _settings() -> Settings:
    return Settings(
        database_url="postgresql+asyncpg://test:test@localhost/test",
        valkey_url="redis://localhost:6379/1",
        keycloak_base_url="http://localhost:8080",
        keycloak_realm="gateway",
        keycloak_client_id="gateway-frontend",
        keycloak_audience="gateway-backend",
        guardrails_base_url="http://localhost:9000",
        api_key_secret_pepper="pepper",
    )


def _discovery(db_session: AsyncSession) -> DiscoveryService:
    client = McpClient(_settings())
    health_checker = HealthChecker(McpServerRepo(db_session), client)
    return DiscoveryService(McpServerRepo(db_session), McpToolRepo(db_session), client, health_checker)


def _tools_response(names: list[str]) -> httpx.Response:
    return httpx.Response(
        200,
        headers={MCP_SESSION_HEADER: "server-session"},
        json={
            "jsonrpc": "2.0",
            "id": "1",
            "result": {"tools": [{"name": n, "description": f"{n} desc", "inputSchema": {}} for n in names]},
        },
    )


def _init_response(session_id: str) -> httpx.Response:
    return httpx.Response(200, headers={MCP_SESSION_HEADER: session_id}, json={"jsonrpc": "2.0", "id": "1", "result": {}})


@pytest.mark.asyncio
@respx.mock
async def test_sync_server_adds_new_tools(db_session: AsyncSession) -> None:
    """Test case: add new server -> tools appear."""
    server = McpServer(name="threat-intel", base_url="http://mcp.test/mcp")
    db_session.add(server)
    await db_session.flush()

    respx.post("http://mcp.test/mcp").mock(
        side_effect=[_init_response("s1"), _tools_response(["get_top_threats", "get_ioc_reputation"])]
    )

    updated = await _discovery(db_session).sync_server(server)
    await db_session.commit()

    assert updated.last_sync_status == McpSyncStatus.success
    assert updated.health_status == McpHealthStatus.healthy
    assert updated.last_heartbeat is not None
    assert updated.last_sync_latency_ms is not None
    tools = await McpToolRepo(db_session).list_by_server(server.id)
    assert {t.name for t in tools} == {"get_top_threats", "get_ioc_reputation"}


@pytest.mark.asyncio
@respx.mock
async def test_sync_server_removes_tools_no_longer_advertised(db_session: AsyncSession) -> None:
    server = McpServer(name="threat-intel", base_url="http://mcp.test/mcp")
    db_session.add(server)
    await db_session.flush()

    respx.post("http://mcp.test/mcp").mock(
        side_effect=[_init_response("s1"), _tools_response(["get_top_threats", "get_ioc_reputation"])]
    )
    discovery = _discovery(db_session)
    await discovery.sync_server(server)
    await db_session.commit()

    respx.post("http://mcp.test/mcp").mock(side_effect=[_init_response("s2"), _tools_response(["get_top_threats"])])
    await discovery.sync_server(server)
    await db_session.commit()

    tools = await McpToolRepo(db_session).list_by_server(server.id)
    assert {t.name for t in tools} == {"get_top_threats"}


@pytest.mark.asyncio
@respx.mock
async def test_sync_server_records_error_status_and_unhealthy_without_raising(db_session: AsyncSession) -> None:
    """Test case: server down -> not used (recorded as unhealthy, sync doesn't crash)."""
    server = McpServer(name="unreachable", base_url="http://mcp-down.test/mcp")
    db_session.add(server)
    await db_session.flush()

    respx.post("http://mcp-down.test/mcp").mock(side_effect=httpx.ConnectError("refused"))

    updated = await _discovery(db_session).sync_server(server)
    await db_session.commit()

    assert updated.last_sync_status == McpSyncStatus.error
    assert updated.last_sync_error is not None
    assert updated.health_status == McpHealthStatus.unhealthy


@pytest.mark.asyncio
@respx.mock
async def test_sync_all_is_best_effort_across_servers(db_session: AsyncSession) -> None:
    good = McpServer(name="good", base_url="http://mcp-good.test/mcp")
    bad = McpServer(name="bad", base_url="http://mcp-bad.test/mcp")
    db_session.add_all([good, bad])
    await db_session.flush()

    respx.post("http://mcp-good.test/mcp").mock(side_effect=[_init_response("s1"), _tools_response(["get_top_threats"])])
    respx.post("http://mcp-bad.test/mcp").mock(side_effect=httpx.ConnectError("refused"))

    results = await _discovery(db_session).sync_all()
    await db_session.commit()

    statuses = {r.name: r.last_sync_status for r in results}
    assert statuses["good"] == McpSyncStatus.success
    assert statuses["bad"] == McpSyncStatus.error


@pytest.mark.asyncio
@respx.mock
async def test_overlapping_tool_name_is_reassigned_to_most_recent_server(db_session: AsyncSession) -> None:
    """Test case: multiple servers with overlapping tools -- tool_name is unique
    gateway-wide, so the most recently synced owner wins the mapping."""
    server_a = McpServer(name="server-a", base_url="http://mcp-a.test/mcp")
    server_b = McpServer(name="server-b", base_url="http://mcp-b.test/mcp")
    db_session.add_all([server_a, server_b])
    await db_session.flush()
    discovery = _discovery(db_session)

    respx.post("http://mcp-a.test/mcp").mock(side_effect=[_init_response("sa"), _tools_response(["shared_tool"])])
    await discovery.sync_server(server_a)
    await db_session.commit()

    respx.post("http://mcp-b.test/mcp").mock(side_effect=[_init_response("sb"), _tools_response(["shared_tool"])])
    await discovery.sync_server(server_b)
    await db_session.commit()

    tool = await McpToolRepo(db_session).get_by_name("shared_tool")
    assert tool.server_id == server_b.id
    # server_a no longer owns any tool -- the shared name moved, it wasn't duplicated
    assert await McpToolRepo(db_session).list_by_server(server_a.id) == []


@pytest.mark.asyncio
@respx.mock
async def test_sync_all_skips_inactive_servers(db_session: AsyncSession) -> None:
    """Test case: disable server -> it is not synced/probed at all."""
    from app.db.models.enums import McpServerStatus

    active = McpServer(name="active-one", base_url="http://mcp-active.test/mcp", status=McpServerStatus.active)
    inactive = McpServer(name="inactive-one", base_url="http://mcp-inactive.test/mcp", status=McpServerStatus.inactive)
    db_session.add_all([active, inactive])
    await db_session.flush()

    route = respx.post("http://mcp-active.test/mcp").mock(
        side_effect=[_init_response("s1"), _tools_response(["get_top_threats"])]
    )
    inactive_route = respx.post("http://mcp-inactive.test/mcp").mock(side_effect=[_init_response("s2")])

    results = await _discovery(db_session).sync_all()
    await db_session.commit()

    assert {r.name for r in results} == {"active-one"}
    assert route.call_count == 2
    assert inactive_route.call_count == 0
