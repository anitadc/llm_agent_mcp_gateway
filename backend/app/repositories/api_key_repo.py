import uuid
from datetime import datetime, timezone

from sqlalchemy import select

from app.db.models.api_key import ApiKey
from app.repositories.base import BaseRepository


class ApiKeyRepo(BaseRepository[ApiKey]):
    model = ApiKey

    async def get_by_hashed_key(self, hashed_key: str) -> ApiKey | None:
        result = await self.db.execute(
            select(ApiKey).where(ApiKey.hashed_key == hashed_key, ApiKey.is_active.is_(True))
        )
        return result.scalar_one_or_none()

    async def list_visible(self, project_id: uuid.UUID | None = None) -> list[ApiKey]:
        stmt = select(ApiKey)
        if project_id is not None:
            stmt = stmt.where(ApiKey.project_id == project_id)
        result = await self.db.execute(stmt)
        return list(result.scalars().all())

    async def touch_last_used(self, api_key: ApiKey) -> None:
        api_key.last_used_at = datetime.now(timezone.utc)
        await self.db.flush()

    async def revoke(self, api_key: ApiKey) -> None:
        api_key.is_active = False
        api_key.revoked_at = datetime.now(timezone.utc)
        await self.db.flush()
