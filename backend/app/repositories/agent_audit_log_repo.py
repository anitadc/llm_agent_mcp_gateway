import uuid

from sqlalchemy import func, select

from app.db.models.agent_audit_log import AgentAuditLog
from app.repositories.base import BaseRepository


class AgentAuditLogRepo(BaseRepository[AgentAuditLog]):
    model = AgentAuditLog

    async def list_paginated(
        self, agent_id: uuid.UUID | None = None, page: int = 1, page_size: int = 25
    ) -> tuple[list[AgentAuditLog], int]:
        count_stmt = select(func.count()).select_from(AgentAuditLog)
        stmt = select(AgentAuditLog).order_by(AgentAuditLog.created_at.desc())
        if agent_id is not None:
            count_stmt = count_stmt.where(AgentAuditLog.agent_id == agent_id)
            stmt = stmt.where(AgentAuditLog.agent_id == agent_id)
        total = (await self.db.execute(count_stmt)).scalar_one()
        stmt = stmt.offset((page - 1) * page_size).limit(page_size)
        items = list((await self.db.execute(stmt)).scalars().all())
        return items, total
