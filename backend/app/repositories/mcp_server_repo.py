import uuid

from sqlalchemy import func, select

from app.core.logging import get_logger, log_method
from app.db.models.enums import McpServerStatus
from app.db.models.mcp_server import McpServer
from app.db.models.mcp_tool import McpTool
from app.repositories.base import BaseRepository

logger = get_logger(__name__)


class McpServerRepo(BaseRepository[McpServer]):
    model = McpServer

    @log_method(logger)
    async def list_active(self) -> list[McpServer]:
        result = await self.db.execute(select(McpServer).where(McpServer.status == McpServerStatus.active))
        return list(result.scalars().all())

    @log_method(logger)
    async def get_by_name(self, name: str) -> McpServer | None:
        result = await self.db.execute(select(McpServer).where(McpServer.name == name))
        return result.scalar_one_or_none()

    @log_method(logger)
    async def list_with_tool_counts(self) -> list[tuple[McpServer, int]]:
        stmt = (
            select(McpServer, func.count(McpTool.id))
            .outerjoin(McpTool, McpTool.server_id == McpServer.id)
            .group_by(McpServer.id)
            .order_by(McpServer.name)
        )
        return [(row[0], row[1]) for row in (await self.db.execute(stmt)).all()]

    @log_method(logger)
    async def get_with_tool_count(self, id: uuid.UUID) -> tuple[McpServer, int] | None:
        stmt = (
            select(McpServer, func.count(McpTool.id))
            .outerjoin(McpTool, McpTool.server_id == McpServer.id)
            .where(McpServer.id == id)
            .group_by(McpServer.id)
        )
        row = (await self.db.execute(stmt)).one_or_none()
        return (row[0], row[1]) if row else None
