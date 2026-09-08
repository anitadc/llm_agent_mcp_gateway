import uuid

from sqlalchemy import select

from app.core.logging import get_logger, log_method
from app.db.models.enums import IdentityProviderName
from app.db.models.user import User
from app.repositories.base import BaseRepository

logger = get_logger(__name__)


class UserRepo(BaseRepository[User]):
    model = User

    @log_method(logger)
    async def get_by_email(self, email: str) -> User | None:
        result = await self.db.execute(select(User).where(User.email == email))
        return result.scalar_one_or_none()

    @log_method(logger)
    async def get_by_external_sub(self, identity_provider: IdentityProviderName, external_sub: str) -> User | None:
        result = await self.db.execute(
            select(User).where(User.identity_provider == identity_provider, User.external_sub == external_sub)
        )
        return result.scalar_one_or_none()

    @log_method(logger)
    async def list_visible(self, organization_id: uuid.UUID | None = None) -> list[User]:
        stmt = select(User)
        if organization_id is not None:
            stmt = stmt.where(User.organization_id == organization_id)
        result = await self.db.execute(stmt)
        return list(result.scalars().all())
