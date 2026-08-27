import uuid
from typing import Any

from app.core.exceptions import BadRequestError
from app.db.models.api_endpoint import ApiEndpoint
from app.db.models.enums import McpToolSourceType, RestHttpMethod
from app.db.models.mcp_tool import McpTool
from app.repositories.api_endpoint_repo import ApiEndpointRepo
from app.repositories.api_service_repo import ApiServiceRepo
from app.repositories.mcp_tool_repo import McpToolRepo
from app.services.api_registry.rest_executor import RestExecutionResult, RestExecutor
from app.services.api_registry.schema_converter import endpoint_to_input_schema


class ApiRegistryService:
    """Facade for the API Service Registry: registering REST endpoints,
    auto-generating (and keeping in sync) each endpoint's paired McpTool row --
    the "every REST endpoint automatically becomes an MCP Tool" feature -- and
    dispatching a REST-backed `tools/call`. Mirrors DiscoveryService's role for
    MCP servers, except endpoints are explicitly registered via the admin API
    rather than discovered from a live server."""

    def __init__(
        self,
        service_repo: ApiServiceRepo,
        endpoint_repo: ApiEndpointRepo,
        tool_repo: McpToolRepo,
        executor: RestExecutor,
    ) -> None:
        self.service_repo = service_repo
        self.endpoint_repo = endpoint_repo
        self.tool_repo = tool_repo
        self.executor = executor

    async def register_endpoint(
        self,
        api_service_id: uuid.UUID,
        *,
        tool_name: str,
        description: str | None,
        method: RestHttpMethod,
        path: str,
        parameters: dict[str, Any],
        enabled: bool,
    ) -> ApiEndpoint:
        existing = await self.tool_repo.get_by_name(tool_name)
        if existing is not None:
            raise BadRequestError(f"Tool name '{tool_name}' is already registered (source: {existing.source_type.value})")

        endpoint = await self.endpoint_repo.add(
            ApiEndpoint(
                api_service_id=api_service_id,
                tool_name=tool_name,
                description=description,
                method=method,
                path=path,
                parameters=parameters,
                enabled=enabled,
            )
        )
        await self._sync_tool(endpoint)
        return await self.endpoint_repo.get(endpoint.id)

    async def update_endpoint(
        self,
        endpoint: ApiEndpoint,
        *,
        description: str | None = None,
        method: RestHttpMethod | None = None,
        path: str | None = None,
        parameters: dict[str, Any] | None = None,
        enabled: bool | None = None,
    ) -> ApiEndpoint:
        if description is not None:
            endpoint.description = description
        if method is not None:
            endpoint.method = method
        if path is not None:
            endpoint.path = path
        if parameters is not None:
            endpoint.parameters = parameters
        if enabled is not None:
            endpoint.enabled = enabled
        await self.endpoint_repo.db.flush()
        await self.endpoint_repo.db.refresh(endpoint)
        await self._sync_tool(endpoint)
        return endpoint

    async def delete_endpoint(self, endpoint: ApiEndpoint) -> None:
        # The paired McpTool row cascades via api_endpoint_id's ondelete=CASCADE.
        await self.endpoint_repo.delete(endpoint)

    async def _sync_tool(self, endpoint: ApiEndpoint) -> None:
        """Regenerates the endpoint's paired McpTool row's input_schema/enabled
        state from its current parameters -- called on every register/update so
        an endpoint's tool definition can never drift from its parameters."""
        input_schema = endpoint_to_input_schema(endpoint.parameters)
        tool = await self.tool_repo.get_by_name(endpoint.tool_name)
        if tool is None:
            tool = McpTool(
                source_type=McpToolSourceType.rest,
                api_endpoint_id=endpoint.id,
                name=endpoint.tool_name,
                description=endpoint.description,
                input_schema=input_schema,
                enabled=endpoint.enabled,
            )
            self.tool_repo.db.add(tool)
        else:
            tool.description = endpoint.description
            tool.input_schema = input_schema
            tool.enabled = endpoint.enabled
        await self.tool_repo.db.flush()

    async def execute(self, tool: McpTool, arguments: dict[str, Any]) -> RestExecutionResult:
        endpoint = tool.api_endpoint
        return await self.executor.execute(endpoint.api_service, endpoint, arguments)
