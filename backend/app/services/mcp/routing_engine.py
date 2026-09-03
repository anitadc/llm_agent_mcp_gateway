from app.core.exceptions import NotFoundError
from app.core.logging import get_logger, log_method
from app.db.models.enums import ApiServiceStatus, McpToolSourceType
from app.db.models.mcp_tool import McpTool
from app.repositories.mcp_tool_repo import McpToolRepo
from app.services.mcp.health_checker import HealthChecker

logger = get_logger(__name__)


class RoutingEngine:
    """Resolves a `tools/call` request to the target that owns it -- an MCP server
    or a REST API endpoint -- purely from the tool name in the JSON-RPC request
    body (never from the URL path). Enforces the registry's availability gate at
    call time -- not just at registration/sync time -- so a target that goes down
    (an MCP server) or gets disabled (a REST API service) stops being routed to
    immediately, without waiting for the next discovery cycle to notice."""

    def __init__(self, tool_repo: McpToolRepo) -> None:
        self.tool_repo = tool_repo

    @log_method(logger)
    async def resolve_tool(self, name: str) -> McpTool:
        tool = await self.tool_repo.get_by_name(name)
        if tool is None:
            logger.warning("mcp_tool_unknown", tool_name=name)
            raise NotFoundError(f"Unknown or unavailable MCP tool '{name}'")
        if not tool.enabled or not self.is_routable(tool):
            logger.warning(
                "mcp_tool_unavailable",
                tool_name=name,
                enabled=tool.enabled,
                source_type=str(tool.source_type),
            )
            raise NotFoundError(f"Unknown or unavailable MCP tool '{name}'")
        return tool

    @staticmethod
    @log_method(logger)
    def is_routable(tool: McpTool) -> bool:
        if tool.source_type == McpToolSourceType.mcp:
            return HealthChecker.is_routable(tool.server)
        return tool.api_endpoint.api_service.status == ApiServiceStatus.active
