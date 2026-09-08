import uuid

from sqlalchemy import select

from app.core.logging import get_logger, log_method
from app.db.models.project import Project
from app.repositories.base import BaseRepository

logger = get_logger(__name__)


class ProjectRepo(BaseRepository[Project]):
    model = Project

    @log_method(logger)
    async def list_visible(self, organization_id: uuid.UUID | None = None) -> list[Project]:
        stmt = select(Project)
        if organization_id is not None:
            stmt = stmt.where(Project.organization_id == organization_id)
        result = await self.db.execute(stmt)
        return list(result.scalars().all())
