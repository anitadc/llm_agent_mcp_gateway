import uuid

from sqlalchemy import or_, select

from app.core.logging import get_logger, log_method
from app.db.models.access_policy import AccessPolicy
from app.repositories.base import BaseRepository

logger = get_logger(__name__)


class AccessPolicyRepo(BaseRepository[AccessPolicy]):
    model = AccessPolicy

    @log_method(logger)
    async def list_active_for_project(self, project_id: uuid.UUID | None) -> list[AccessPolicy]:
        """Active policies that apply to this project: global ones
        (project_id IS NULL) plus any scoped specifically to it."""
        stmt = select(AccessPolicy).where(
            AccessPolicy.is_active.is_(True),
            or_(AccessPolicy.project_id.is_(None), AccessPolicy.project_id == project_id),
        )
        result = await self.db.execute(stmt)
        return list(result.scalars().all())
