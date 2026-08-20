import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import BadRequestError
from app.db.models.api_service import ApiService
from app.db.models.enums import McpToolSourceType, RestAuthType, RestHttpMethod
from app.db.models.mcp_server import McpServer
from app.db.models.mcp_tool import McpTool
from app.repositories.api_endpoint_repo import ApiEndpointRepo
from app.repositories.api_service_repo import ApiServiceRepo
from app.repositories.mcp_tool_repo import McpToolRepo
from app.services.api_registry.api_registry_service import ApiRegistryService


def _service() -> ApiService:
    return ApiService(name="customer-service", base_url="http://api.test", authentication_type=RestAuthType.none)


async def _make_registry(db_session: AsyncSession) -> tuple[ApiRegistryService, ApiService]:
    service_repo = ApiServiceRepo(db_session)
    service = await service_repo.add(_service())
    registry = ApiRegistryService(service_repo, ApiEndpointRepo(db_session), McpToolRepo(db_session), executor=None)
    return registry, service


@pytest.mark.asyncio
async def test_register_endpoint_creates_paired_mcp_tool(db_session: AsyncSession) -> None:
    registry, service = await _make_registry(db_session)

    endpoint = await registry.register_endpoint(
        service.id,
        tool_name="get_customer",
        description="Retrieve customer information",
        method=RestHttpMethod.GET,
        path="/customers/{id}",
        parameters={"id": {"type": "string", "required": True, "location": "path"}},
        enabled=True,
    )
    await db_session.commit()

    tool = await McpToolRepo(db_session).get_by_name("get_customer")
    assert tool is not None
    assert tool.source_type == McpToolSourceType.rest
    assert tool.api_endpoint_id == endpoint.id
    assert tool.input_schema["properties"]["id"]["type"] == "string"
    assert tool.input_schema["required"] == ["id"]


@pytest.mark.asyncio
async def test_register_endpoint_rejects_duplicate_tool_name(db_session: AsyncSession) -> None:
    registry, service = await _make_registry(db_session)
    await registry.register_endpoint(
        service.id, tool_name="get_customer", description=None, method=RestHttpMethod.GET, path="/c/{id}",
        parameters={}, enabled=True,
    )
    await db_session.commit()

    with pytest.raises(BadRequestError):
        await registry.register_endpoint(
            service.id, tool_name="get_customer", description=None, method=RestHttpMethod.GET, path="/c2/{id}",
            parameters={}, enabled=True,
        )


@pytest.mark.asyncio
async def test_register_endpoint_rejects_name_collision_with_an_mcp_server_tool(db_session: AsyncSession) -> None:
    server = McpServer(name="threat-intel", base_url="http://mcp.test/mcp")
    db_session.add(server)
    await db_session.flush()
    db_session.add(McpTool(source_type=McpToolSourceType.mcp, server_id=server.id, name="get_top_threats", input_schema={}))
    await db_session.commit()

    registry, service = await _make_registry(db_session)

    with pytest.raises(BadRequestError):
        await registry.register_endpoint(
            service.id, tool_name="get_top_threats", description=None, method=RestHttpMethod.GET, path="/x",
            parameters={}, enabled=True,
        )


@pytest.mark.asyncio
async def test_update_endpoint_regenerates_tool_schema(db_session: AsyncSession) -> None:
    registry, service = await _make_registry(db_session)
    endpoint = await registry.register_endpoint(
        service.id, tool_name="get_customer", description="old", method=RestHttpMethod.GET, path="/customers/{id}",
        parameters={"id": {"type": "string", "required": True, "location": "path"}}, enabled=True,
    )
    await db_session.commit()

    await registry.update_endpoint(
        endpoint,
        description="new description",
        parameters={
            "id": {"type": "string", "required": True, "location": "path"},
            "page": {"type": "integer", "required": False, "location": "query"},
        },
    )
    await db_session.commit()

    tool = await McpToolRepo(db_session).get_by_name("get_customer")
    assert tool.description == "new description"
    assert "page" in tool.input_schema["properties"]


@pytest.mark.asyncio
async def test_delete_endpoint_cascades_to_mcp_tool(db_session: AsyncSession) -> None:
    registry, service = await _make_registry(db_session)
    endpoint = await registry.register_endpoint(
        service.id, tool_name="get_customer", description=None, method=RestHttpMethod.GET, path="/customers/{id}",
        parameters={}, enabled=True,
    )
    await db_session.commit()

    await registry.delete_endpoint(endpoint)
    await db_session.commit()

    assert await McpToolRepo(db_session).get_by_name("get_customer") is None


class _StubExecutor:
    def __init__(self, result) -> None:
        self.result = result
        self.calls: list[tuple] = []

    async def execute(self, service, endpoint, arguments):
        self.calls.append((service, endpoint, arguments))
        return self.result


@pytest.mark.asyncio
async def test_execute_dispatches_to_executor_with_resolved_endpoint_and_service(db_session: AsyncSession) -> None:
    """End-to-end wiring check: register an endpoint (-> paired MCP tool),
    discover it via the tool registry, then invoke it and confirm the
    executor receives the correctly resolved ApiService + ApiEndpoint."""
    service_repo = ApiServiceRepo(db_session)
    service = await service_repo.add(_service())
    tool_repo = McpToolRepo(db_session)
    stub = _StubExecutor(result="fake-result")
    registry = ApiRegistryService(service_repo, ApiEndpointRepo(db_session), tool_repo, executor=stub)

    await registry.register_endpoint(
        service.id, tool_name="get_customer", description=None, method=RestHttpMethod.GET, path="/customers/{id}",
        parameters={}, enabled=True,
    )
    await db_session.commit()

    tool = await tool_repo.get_by_name("get_customer")  # the "agent discovers the tool" step
    result = await registry.execute(tool, {"id": "1"})  # the "agent invokes the tool" step

    assert result == "fake-result"
    assert len(stub.calls) == 1
    called_service, called_endpoint, called_args = stub.calls[0]
    assert called_service.id == service.id
    assert called_endpoint.tool_name == "get_customer"
    assert called_args == {"id": "1"}
