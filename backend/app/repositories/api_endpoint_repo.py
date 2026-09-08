import uuid

from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.core.logging import get_logger, log_method
from app.db.models.api_endpoint import ApiEndpoint
from app.repositories.base import BaseRepository

logger = get_logger(__name__)


class ApiEndpointRepo(BaseRepository[ApiEndpoint]):
    model = ApiEndpoint

    @log_method(logger)
    async def get(self, id: uuid.UUID) -> ApiEndpoint | None:
        result = await self.db.execute(
            select(ApiEndpoint).options(selectinload(ApiEndpoint.api_service)).where(ApiEndpoint.id == id)
        )
        return result.scalar_one_or_none()

    @log_method(logger)
    async def get_by_tool_name(self, tool_name: str) -> ApiEndpoint | None:
        result = await self.db.execute(
            select(ApiEndpoint).options(selectinload(ApiEndpoint.api_service)).where(ApiEndpoint.tool_name == tool_name)
        )
        return result.scalar_one_or_none()

    @log_method(logger)
    async def list_by_service(self, api_service_id: uuid.UUID) -> list[ApiEndpoint]:
        result = await self.db.execute(
            select(ApiEndpoint)
            .options(selectinload(ApiEndpoint.api_service))
            .where(ApiEndpoint.api_service_id == api_service_id)
        )
        return list(result.scalars().all())
