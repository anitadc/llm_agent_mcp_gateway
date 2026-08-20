import uuid

from sqlalchemy import select

from app.db.models.budget import Budget
from app.repositories.base import BaseRepository


class BudgetRepo(BaseRepository[Budget]):
    model = Budget

    async def list_visible(
        self, organization_id: uuid.UUID | None = None, project_id: uuid.UUID | None = None
    ) -> list[Budget]:
        stmt = select(Budget)
        if organization_id is not None:
            stmt = stmt.where(Budget.organization_id == organization_id)
        if project_id is not None:
            stmt = stmt.where(Budget.project_id == project_id)
        result = await self.db.execute(stmt)
        return list(result.scalars().all())
