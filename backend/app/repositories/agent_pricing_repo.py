import uuid

from sqlalchemy import select

from app.db.models.agent_pricing import AgentPricing
from app.repositories.base import BaseRepository


class AgentPricingRepo(BaseRepository[AgentPricing]):
    model = AgentPricing

    async def get_by_agent(self, agent_id: uuid.UUID) -> AgentPricing | None:
        result = await self.db.execute(select(AgentPricing).where(AgentPricing.agent_id == agent_id))
        return result.scalar_one_or_none()
