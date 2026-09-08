import uuid

from sqlalchemy import select

from app.core.logging import get_logger, log_method
from app.db.models.agent import Agent
from app.db.models.enums import AgentLifecycleStatus
from app.repositories.base import BaseRepository

logger = get_logger(__name__)


class AgentRepo(BaseRepository[Agent]):
    model = Agent

    @log_method(logger)
    async def get_by_key(self, agent_key: str) -> Agent | None:
        result = await self.db.execute(select(Agent).where(Agent.agent_key == agent_key))
        return result.scalar_one_or_none()

    @log_method(logger)
    async def list_by_capability(self, capability: str, status: AgentLifecycleStatus) -> list[Agent]:
        """Ordered by `priority` ascending -- lower number wins, same convention
        as RoutingRule target `weight` -- so the invocation service can just take
        the first eligible candidate after policy filtering. Capability membership
        is filtered in Python (registrations are admin-scale, not per-request-hot),
        matching how PolicyEngine evaluates its own array fields in-memory rather
        than pushing array-containment logic into SQL."""
        result = await self.db.execute(select(Agent).where(Agent.status == status).order_by(Agent.priority.asc()))
        return [agent for agent in result.scalars().all() if capability in agent.capabilities]
