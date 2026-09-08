from sqlalchemy import select

from app.core.logging import get_logger, log_method
from app.db.models.tenant_identity_config import TenantIdentityConfig
from app.repositories.base import BaseRepository

logger = get_logger(__name__)


class TenantIdentityConfigRepo(BaseRepository[TenantIdentityConfig]):
    model = TenantIdentityConfig

    @log_method(logger)
    async def get_by_issuer(self, issuer: str) -> TenantIdentityConfig | None:
        result = await self.db.execute(select(TenantIdentityConfig).where(TenantIdentityConfig.issuer == issuer))
        return result.scalar_one_or_none()

    @log_method(logger)
    async def get_by_tenant_id(self, tenant_id: str) -> TenantIdentityConfig | None:
        result = await self.db.execute(select(TenantIdentityConfig).where(TenantIdentityConfig.tenant_id == tenant_id))
        return result.scalar_one_or_none()
