import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundError
from app.db.models.api_endpoint import ApiEndpoint
from app.db.models.api_service import ApiService
from app.db.models.enums import ApiServiceStatus, McpToolSourceType, RestAuthType, RestHttpMethod
from app.db.models.mcp_tool import McpTool
from app.repositories.mcp_tool_repo import McpToolRepo
from app.services.mcp.routing_engine import RoutingEngine


async def _seed_rest_tool(db_session: AsyncSession, *, service_status=ApiServiceStatus.active, tool_enabled=True) -> None:
    service = ApiService(
        name="customer-service", base_url="http://api.test", authentication_type=RestAuthType.none, status=service_status
    )
    db_session.add(service)
    await db_session.flush()

    endpoint = ApiEndpoint(
        api_service_id=service.id, tool_name="get_customer", method=RestHttpMethod.GET, path="/customers/{id}", parameters={}
    )
    db_session.add(endpoint)
    await db_session.flush()

    db_session.add(
        McpTool(
            source_type=McpToolSourceType.rest,
            api_endpoint_id=endpoint.id,
            name="get_customer",
            input_schema={},
            enabled=tool_enabled,
        )
    )
    await db_session.commit()


@pytest.mark.asyncio
async def test_resolve_tool_routes_a_rest_backed_tool_to_its_endpoint(db_session: AsyncSession) -> None:
    await _seed_rest_tool(db_session)
    engine = RoutingEngine(McpToolRepo(db_session))

    tool = await engine.resolve_tool("get_customer")

    assert tool.source_type == McpToolSourceType.rest
    assert tool.api_endpoint.path == "/customers/{id}"
    assert tool.api_endpoint.api_service.name == "customer-service"


@pytest.mark.asyncio
async def test_resolve_tool_raises_when_owning_api_service_is_inactive(db_session: AsyncSession) -> None:
    await _seed_rest_tool(db_session, service_status=ApiServiceStatus.inactive)
    engine = RoutingEngine(McpToolRepo(db_session))

    with pytest.raises(NotFoundError):
        await engine.resolve_tool("get_customer")


@pytest.mark.asyncio
async def test_resolve_tool_raises_when_rest_tool_disabled(db_session: AsyncSession) -> None:
    await _seed_rest_tool(db_session, tool_enabled=False)
    engine = RoutingEngine(McpToolRepo(db_session))

    with pytest.raises(NotFoundError):
        await engine.resolve_tool("get_customer")


@pytest.mark.asyncio
async def test_search_only_available_includes_active_rest_tools_and_excludes_inactive_ones(db_session: AsyncSession) -> None:
    await _seed_rest_tool(db_session)
    tool_repo = McpToolRepo(db_session)

    available = await tool_repo.search(None, only_available=True)

    assert any(t.name == "get_customer" for t in available)


@pytest.mark.asyncio
async def test_search_only_available_excludes_tools_from_an_inactive_api_service(db_session: AsyncSession) -> None:
    await _seed_rest_tool(db_session, service_status=ApiServiceStatus.inactive)
    tool_repo = McpToolRepo(db_session)

    available = await tool_repo.search(None, only_available=True)

    assert not any(t.name == "get_customer" for t in available)
