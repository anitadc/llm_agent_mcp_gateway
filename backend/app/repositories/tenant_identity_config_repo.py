from sqlalchemy import select

from app.db.models.tenant_identity_config import TenantIdentityConfig
from app.repositories.base import BaseRepository


class TenantIdentityConfigRepo(BaseRepository[TenantIdentityConfig]):
    model = TenantIdentityConfig

    async def get_by_issuer(self, issuer: str) -> TenantIdentityConfig | None:
        result = await self.db.execute(select(TenantIdentityConfig).where(TenantIdentityConfig.issuer == issuer))
        return result.scalar_one_or_none()

    async def get_by_tenant_id(self, tenant_id: str) -> TenantIdentityConfig | None:
        result = await self.db.execute(select(TenantIdentityConfig).where(TenantIdentityConfig.tenant_id == tenant_id))
        return result.scalar_one_or_none()
