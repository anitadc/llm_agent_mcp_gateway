import uuid

from sqlalchemy import select

from app.db.models.project import Project
from app.repositories.base import BaseRepository


class ProjectRepo(BaseRepository[Project]):
    model = Project

    async def list_visible(self, organization_id: uuid.UUID | None = None) -> list[Project]:
        stmt = select(Project)
        if organization_id is not None:
            stmt = stmt.where(Project.organization_id == organization_id)
        result = await self.db.execute(stmt)
        return list(result.scalars().all())
