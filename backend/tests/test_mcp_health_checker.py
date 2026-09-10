import httpx
import pytest
import respx
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.db.models.enums import McpHealthStatus, McpServerStatus
from app.db.models.mcp_server import McpServer
from app.repositories.mcp_server_repo import McpServerRepo
from app.services.mcp.health_checker import HealthChecker
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


@pytest.mark.asyncio
@respx.mock
async def test_probe_marks_server_healthy_on_success(db_session: AsyncSession) -> None:
    server = McpServer(name="threat-intel", base_url="http://mcp.test/mcp")
    db_session.add(server)
    await db_session.flush()
    respx.post("http://mcp.test/mcp").mock(
        return_value=httpx.Response(200, headers={MCP_SESSION_HEADER: "s1"}, json={"jsonrpc": "2.0", "id": "1", "result": {}})
    )

    checker = HealthChecker(McpServerRepo(db_session), McpClient(_settings()))
    result = await checker.probe(server)
    await db_session.commit()

    assert result is not None
    assert result.session_id == "s1"
    assert server.health_status == McpHealthStatus.healthy
    assert server.last_heartbeat is not None


@pytest.mark.asyncio
@respx.mock
async def test_probe_marks_server_unhealthy_on_failure(db_session: AsyncSession) -> None:
    server = McpServer(name="unreachable", base_url="http://mcp-down.test/mcp")
    db_session.add(server)
    await db_session.flush()
    respx.post("http://mcp-down.test/mcp").mock(side_effect=httpx.ConnectError("refused"))

    checker = HealthChecker(McpServerRepo(db_session), McpClient(_settings()))
    result = await checker.probe(server)
    await db_session.commit()

    assert result is None
    assert server.health_status == McpHealthStatus.unhealthy
    assert server.last_heartbeat is not None


@pytest.mark.asyncio
@respx.mock
async def test_check_all_only_probes_active_servers(db_session: AsyncSession) -> None:
    active = McpServer(name="active-one", base_url="http://mcp-active.test/mcp", status=McpServerStatus.active)
    inactive = McpServer(name="inactive-one", base_url="http://mcp-inactive.test/mcp", status=McpServerStatus.inactive)
    db_session.add_all([active, inactive])
    await db_session.flush()
    route = respx.post("http://mcp-active.test/mcp").mock(
        return_value=httpx.Response(200, headers={MCP_SESSION_HEADER: "s1"}, json={"jsonrpc": "2.0", "id": "1", "result": {}})
    )
    inactive_route = respx.post("http://mcp-inactive.test/mcp").mock(
        return_value=httpx.Response(200, json={"jsonrpc": "2.0", "id": "1", "result": {}})
    )

    checker = HealthChecker(McpServerRepo(db_session), McpClient(_settings()))
    checked = await checker.check_all()
    await db_session.commit()

    assert {s.name for s in checked} == {"active-one"}
    assert route.call_count == 1
    assert inactive_route.call_count == 0


def test_is_routable_requires_active_and_healthy() -> None:
    active_healthy = McpServer(name="a", base_url="x", status=McpServerStatus.active, health_status=McpHealthStatus.healthy)
    active_unhealthy = McpServer(name="b", base_url="x", status=McpServerStatus.active, health_status=McpHealthStatus.unhealthy)
    inactive_healthy = McpServer(name="c", base_url="x", status=McpServerStatus.inactive, health_status=McpHealthStatus.healthy)

    assert HealthChecker.is_routable(active_healthy) is True
    assert HealthChecker.is_routable(active_unhealthy) is False
    assert HealthChecker.is_routable(inactive_healthy) is False
