import uuid

from sqlalchemy import func, select

from app.core.logging import get_logger, log_method
from app.db.models.api_endpoint import ApiEndpoint
from app.db.models.api_service import ApiService
from app.repositories.base import BaseRepository

logger = get_logger(__name__)


class ApiServiceRepo(BaseRepository[ApiService]):
    model = ApiService

    @log_method(logger)
    async def get_by_name(self, name: str) -> ApiService | None:
        result = await self.db.execute(select(ApiService).where(ApiService.name == name))
        return result.scalar_one_or_none()

    @log_method(logger)
    async def list_with_endpoint_counts(self) -> list[tuple[ApiService, int]]:
        stmt = (
            select(ApiService, func.count(ApiEndpoint.id))
            .outerjoin(ApiEndpoint, ApiEndpoint.api_service_id == ApiService.id)
            .group_by(ApiService.id)
            .order_by(ApiService.name)
        )
        return [(row[0], row[1]) for row in (await self.db.execute(stmt)).all()]

    @log_method(logger)
    async def get_with_endpoint_count(self, id: uuid.UUID) -> tuple[ApiService, int] | None:
        stmt = (
            select(ApiService, func.count(ApiEndpoint.id))
            .outerjoin(ApiEndpoint, ApiEndpoint.api_service_id == ApiService.id)
            .where(ApiService.id == id)
            .group_by(ApiService.id)
        )
        row = (await self.db.execute(stmt)).one_or_none()
        return (row[0], row[1]) if row else None
