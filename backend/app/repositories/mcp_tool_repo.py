import uuid

from sqlalchemy import and_, or_, select
from sqlalchemy.orm import selectinload

from app.core.logging import get_logger, log_method
from app.db.models.api_endpoint import ApiEndpoint
from app.db.models.api_service import ApiService
from app.db.models.enums import ApiServiceStatus, McpHealthStatus, McpServerStatus, McpToolSourceType
from app.db.models.mcp_server import McpServer
from app.db.models.mcp_tool import McpTool
from app.repositories.base import BaseRepository

logger = get_logger(__name__)

_EAGER_LOAD = (
    selectinload(McpTool.server),
    selectinload(McpTool.api_endpoint).selectinload(ApiEndpoint.api_service),
)

# A tool is routable when it's enabled AND its target is available: for an
# MCP-backed tool, the owning server must be administratively active and
# currently healthy (HealthChecker.is_routable's condition); for a REST-backed
# tool, the owning API service must be administratively active (REST services
# have no liveness/health concept -- see ApiServiceStatus's docstring).
_AVAILABLE = McpTool.enabled.is_(True) & or_(
    and_(
        McpTool.source_type == McpToolSourceType.mcp,
        McpServer.status == McpServerStatus.active,
        McpServer.health_status == McpHealthStatus.healthy,
    ),
    and_(McpTool.source_type == McpToolSourceType.rest, ApiService.status == ApiServiceStatus.active),
)


class McpToolRepo(BaseRepository[McpTool]):
    model = McpTool

    @log_method(logger)
    async def get(self, id: uuid.UUID) -> McpTool | None:
        result = await self.db.execute(select(McpTool).options(*_EAGER_LOAD).where(McpTool.id == id))
        return result.scalar_one_or_none()

    @log_method(logger)
    async def get_by_name(self, name: str) -> McpTool | None:
        result = await self.db.execute(select(McpTool).options(*_EAGER_LOAD).where(McpTool.name == name))
        return result.scalar_one_or_none()

    @log_method(logger)
    async def list_by_server(self, server_id: uuid.UUID) -> list[McpTool]:
        result = await self.db.execute(select(McpTool).where(McpTool.server_id == server_id))
        return list(result.scalars().all())

    @log_method(logger)
    async def list_by_api_service(self, api_service_id: uuid.UUID) -> list[McpTool]:
        result = await self.db.execute(
            select(McpTool).join(McpTool.api_endpoint).where(ApiEndpoint.api_service_id == api_service_id)
        )
        return list(result.scalars().all())

    @log_method(logger)
    async def search(self, query: str | None, only_available: bool = False) -> list[McpTool]:
        """`only_available` applies the registry's routing gate at the SQL level
        (tool enabled, target available -- MCP server active+healthy, or REST API
        service active) -- the same condition RoutingEngine.resolve_tool checks
        in-memory for a single already-loaded tool, expressed here as an outer
        join (a tool has exactly one target, never both) so it can filter a
        whole listing regardless of tool kind."""
        stmt = (
            select(McpTool)
            .outerjoin(McpTool.server)
            .outerjoin(McpTool.api_endpoint)
            .outerjoin(ApiEndpoint.api_service)
            .options(*_EAGER_LOAD)
        )
        if only_available:
            stmt = stmt.where(_AVAILABLE)
        if query:
            like = f"%{query}%"
            stmt = stmt.where(or_(McpTool.name.ilike(like), McpTool.description.ilike(like)))
        return list((await self.db.execute(stmt)).scalars().all())
