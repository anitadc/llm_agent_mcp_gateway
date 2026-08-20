from sqlalchemy import select

from app.db.models.mcp_session import McpSession
from app.repositories.base import BaseRepository


class McpSessionRepo(BaseRepository[McpSession]):
    model = McpSession

    async def get_by_client_session_id(self, client_session_id: str) -> McpSession | None:
        result = await self.db.execute(
            select(McpSession).where(McpSession.client_session_id == client_session_id)
        )
        return result.scalar_one_or_none()
