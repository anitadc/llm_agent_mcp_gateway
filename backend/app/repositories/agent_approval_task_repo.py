import uuid

from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.db.models.agent_approval_task import AgentApprovalTask
from app.db.models.enums import AgentApprovalDecision
from app.repositories.base import BaseRepository


class AgentApprovalTaskRepo(BaseRepository[AgentApprovalTask]):
    model = AgentApprovalTask

    async def get(self, id: uuid.UUID) -> AgentApprovalTask | None:
        result = await self.db.execute(
            select(AgentApprovalTask).options(selectinload(AgentApprovalTask.agent)).where(AgentApprovalTask.id == id)
        )
        return result.scalar_one_or_none()

    async def list_by_agent(self, agent_id: uuid.UUID) -> list[AgentApprovalTask]:
        result = await self.db.execute(
            select(AgentApprovalTask)
            .options(selectinload(AgentApprovalTask.agent))
            .where(AgentApprovalTask.agent_id == agent_id)
        )
        return list(result.scalars().all())

    async def list_pending(self) -> list[AgentApprovalTask]:
        result = await self.db.execute(
            select(AgentApprovalTask)
            .options(selectinload(AgentApprovalTask.agent))
            .where(AgentApprovalTask.decision == AgentApprovalDecision.pending)
        )
        return list(result.scalars().all())
