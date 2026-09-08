from sqlalchemy import select

from app.core.logging import get_logger, log_method
from app.db.models.agent_invocation import AgentInvocation
from app.repositories.base import BaseRepository

logger = get_logger(__name__)


class AgentInvocationRepo(BaseRepository[AgentInvocation]):
    model = AgentInvocation

    @log_method(logger)
    async def list_recent(self, limit: int = 100) -> list[AgentInvocation]:
        result = await self.db.execute(select(AgentInvocation).order_by(AgentInvocation.created_at.desc()).limit(limit))
        return list(result.scalars().all())
