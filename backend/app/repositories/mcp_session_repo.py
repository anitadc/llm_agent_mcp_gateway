from sqlalchemy import select

from app.core.logging import get_logger, log_method
from app.db.models.mcp_session import McpSession
from app.repositories.base import BaseRepository

logger = get_logger(__name__)


class McpSessionRepo(BaseRepository[McpSession]):
    model = McpSession

    @log_method(logger)
    async def get_by_client_session_id(self, client_session_id: str) -> McpSession | None:
        result = await self.db.execute(
            select(McpSession).where(McpSession.client_session_id == client_session_id)
        )
        return result.scalar_one_or_none()
