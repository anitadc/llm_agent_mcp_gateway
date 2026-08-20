import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundError
from app.db.models.enums import McpHealthStatus, McpServerStatus
from app.db.models.mcp_server import McpServer
from app.db.models.mcp_tool import McpTool
from app.repositories.mcp_tool_repo import McpToolRepo
from app.services.mcp.routing_engine import RoutingEngine


def _healthy_active_server(**overrides) -> McpServer:
    defaults = dict(
        name="threat-intel",
        base_url="http://mcp.test/mcp",
        status=McpServerStatus.active,
        health_status=McpHealthStatus.healthy,
    )
    defaults.update(overrides)
    return McpServer(**defaults)


@pytest.mark.asyncio
async def test_resolve_tool_routes_to_owning_server(db_session: AsyncSession) -> None:
    server = _healthy_active_server()
    db_session.add(server)
    await db_session.flush()
    db_session.add(McpTool(server_id=server.id, name="get_top_threats", input_schema={}))
    await db_session.commit()

    engine = RoutingEngine(McpToolRepo(db_session))
    tool = await engine.resolve_tool("get_top_threats")

    assert tool.server_id == server.id
    assert tool.server.name == "threat-intel"


@pytest.mark.asyncio
async def test_resolve_tool_raises_for_unknown_tool(db_session: AsyncSession) -> None:
    engine = RoutingEngine(McpToolRepo(db_session))

    with pytest.raises(NotFoundError):
        await engine.resolve_tool("does_not_exist")


@pytest.mark.asyncio
async def test_resolve_tool_raises_when_tool_disabled(db_session: AsyncSession) -> None:
    server = _healthy_active_server()
    db_session.add(server)
    await db_session.flush()
    db_session.add(McpTool(server_id=server.id, name="get_top_threats", input_schema={}, enabled=False))
    await db_session.commit()

    engine = RoutingEngine(McpToolRepo(db_session))

    with pytest.raises(NotFoundError):
        await engine.resolve_tool("get_top_threats")


@pytest.mark.asyncio
async def test_resolve_tool_raises_when_owning_server_disabled(db_session: AsyncSession) -> None:
    """Test case: disable server -> its tools disappear from routing."""
    server = _healthy_active_server(status=McpServerStatus.inactive)
    db_session.add(server)
    await db_session.flush()
    db_session.add(McpTool(server_id=server.id, name="get_top_threats", input_schema={}))
    await db_session.commit()

    engine = RoutingEngine(McpToolRepo(db_session))

    with pytest.raises(NotFoundError):
        await engine.resolve_tool("get_top_threats")


@pytest.mark.asyncio
async def test_resolve_tool_raises_when_owning_server_unhealthy(db_session: AsyncSession) -> None:
    """Test case: server down -> not used, even though it's still administratively
    active and its tools are still in the registry from a prior successful sync."""
    server = _healthy_active_server(health_status=McpHealthStatus.unhealthy)
    db_session.add(server)
    await db_session.flush()
    db_session.add(McpTool(server_id=server.id, name="get_top_threats", input_schema={}))
    await db_session.commit()

    engine = RoutingEngine(McpToolRepo(db_session))

    with pytest.raises(NotFoundError):
        await engine.resolve_tool("get_top_threats")


@pytest.mark.asyncio
async def test_resolve_tool_raises_when_server_health_unknown(db_session: AsyncSession) -> None:
    """A server that has never been probed (health_status still 'unknown', the
    model default) must not be routed to until a probe confirms it's healthy."""
    server = _healthy_active_server(health_status=McpHealthStatus.unknown)
    db_session.add(server)
    await db_session.flush()
    db_session.add(McpTool(server_id=server.id, name="get_top_threats", input_schema={}))
    await db_session.commit()

    engine = RoutingEngine(McpToolRepo(db_session))

    with pytest.raises(NotFoundError):
        await engine.resolve_tool("get_top_threats")


@pytest.mark.asyncio
async def test_multiple_servers_with_distinct_tools_route_independently(db_session: AsyncSession) -> None:
    """Test case: multiple servers, each tool routes to its own owning server."""
    server_a = _healthy_active_server(name="server-a", base_url="http://mcp-a.test/mcp")
    server_b = _healthy_active_server(name="server-b", base_url="http://mcp-b.test/mcp")
    db_session.add_all([server_a, server_b])
    await db_session.flush()
    db_session.add(McpTool(server_id=server_a.id, name="tool_a", input_schema={}))
    db_session.add(McpTool(server_id=server_b.id, name="tool_b", input_schema={}))
    await db_session.commit()

    engine = RoutingEngine(McpToolRepo(db_session))

    assert (await engine.resolve_tool("tool_a")).server_id == server_a.id
    assert (await engine.resolve_tool("tool_b")).server_id == server_b.id
