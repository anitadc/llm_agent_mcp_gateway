from sqlalchemy import select

from app.db.models.agent_invocation import AgentInvocation
from app.repositories.base import BaseRepository


class AgentInvocationRepo(BaseRepository[AgentInvocation]):
    model = AgentInvocation

    async def list_recent(self, limit: int = 100) -> list[AgentInvocation]:
        result = await self.db.execute(select(AgentInvocation).order_by(AgentInvocation.created_at.desc()).limit(limit))
        return list(result.scalars().all())
