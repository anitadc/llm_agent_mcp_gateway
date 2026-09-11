import uuid

from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.db.models.agent_approval_comment import AgentApprovalComment
from app.repositories.base import BaseRepository


class AgentApprovalCommentRepo(BaseRepository[AgentApprovalComment]):
    model = AgentApprovalComment

    async def list_by_task(self, task_id: uuid.UUID) -> list[AgentApprovalComment]:
        result = await self.db.execute(
            select(AgentApprovalComment)
            .where(AgentApprovalComment.task_id == task_id)
            .order_by(AgentApprovalComment.created_at.asc())
        )
        return list(result.scalars().all())

    async def get(self, id: uuid.UUID) -> AgentApprovalComment | None:
        result = await self.db.execute(
            select(AgentApprovalComment)
            .options(selectinload(AgentApprovalComment.task))
            .where(AgentApprovalComment.id == id)
        )
        return result.scalar_one_or_none()
