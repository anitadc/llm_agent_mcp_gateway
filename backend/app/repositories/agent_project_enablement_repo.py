import uuid

from sqlalchemy import select

from app.db.models.agent_project_enablement import AgentProjectEnablement
from app.repositories.base import BaseRepository


class AgentProjectEnablementRepo(BaseRepository[AgentProjectEnablement]):
    model = AgentProjectEnablement

    async def is_enabled(self, agent_id: uuid.UUID, project_id: uuid.UUID) -> bool:
        result = await self.db.execute(
            select(AgentProjectEnablement.id).where(
                AgentProjectEnablement.agent_id == agent_id, AgentProjectEnablement.project_id == project_id
            )
        )
        return result.scalar_one_or_none() is not None

    async def enabled_project_ids(self, agent_id: uuid.UUID) -> set[uuid.UUID]:
        result = await self.db.execute(
            select(AgentProjectEnablement.project_id).where(AgentProjectEnablement.agent_id == agent_id)
        )
        return set(result.scalars().all())

    async def get_by_agent_and_project(
        self, agent_id: uuid.UUID, project_id: uuid.UUID
    ) -> AgentProjectEnablement | None:
        result = await self.db.execute(
            select(AgentProjectEnablement).where(
                AgentProjectEnablement.agent_id == agent_id, AgentProjectEnablement.project_id == project_id
            )
        )
        return result.scalar_one_or_none()

    async def list_by_agent(self, agent_id: uuid.UUID) -> list[AgentProjectEnablement]:
        result = await self.db.execute(
            select(AgentProjectEnablement).where(AgentProjectEnablement.agent_id == agent_id)
        )
        return list(result.scalars().all())
