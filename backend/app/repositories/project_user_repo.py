import uuid

from sqlalchemy import select

from app.core.logging import get_logger, log_method
from app.db.models.project_user import ProjectUser
from app.repositories.base import BaseRepository

logger = get_logger(__name__)


class ProjectUserRepo(BaseRepository[ProjectUser]):
    model = ProjectUser

    @log_method(logger)
    async def list_memberships(
        self, project_id: uuid.UUID | None = None, user_id: uuid.UUID | None = None
    ) -> list[ProjectUser]:
        stmt = select(ProjectUser)
        if project_id is not None:
            stmt = stmt.where(ProjectUser.project_id == project_id)
        if user_id is not None:
            stmt = stmt.where(ProjectUser.user_id == user_id)
        result = await self.db.execute(stmt)
        return list(result.scalars().all())
