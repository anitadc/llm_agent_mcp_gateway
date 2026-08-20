from sqlalchemy import func, select

from app.db.models.secret_audit_log import SecretAuditLog
from app.repositories.base import BaseRepository


class SecretAuditLogRepo(BaseRepository[SecretAuditLog]):
    model = SecretAuditLog

    async def list_paginated(self, page: int = 1, page_size: int = 25) -> tuple[list[SecretAuditLog], int]:
        total = (await self.db.execute(select(func.count()).select_from(SecretAuditLog))).scalar_one()
        stmt = select(SecretAuditLog).order_by(SecretAuditLog.created_at.desc()).offset((page - 1) * page_size).limit(page_size)
        items = list((await self.db.execute(stmt)).scalars().all())
        return items, total
