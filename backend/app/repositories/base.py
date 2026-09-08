import uuid
from typing import Generic, TypeVar

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger, log_method

logger = get_logger(__name__)
ModelT = TypeVar("ModelT")


class BaseRepository(Generic[ModelT]):
    model: type[ModelT]

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    @log_method(logger)
    async def get(self, id: uuid.UUID) -> ModelT | None:
        return await self.db.get(self.model, id)

    @log_method(logger)
    async def list(self) -> list[ModelT]:
        result = await self.db.execute(select(self.model))
        return list(result.scalars().all())

    @log_method(logger)
    async def add(self, obj: ModelT) -> ModelT:
        self.db.add(obj)
        await self.db.flush()
        await self.db.refresh(obj)
        return obj

    @log_method(logger)
    async def delete(self, obj: ModelT) -> None:
        await self.db.delete(obj)
        await self.db.flush()
