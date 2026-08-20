import uuid
from datetime import date, datetime, timedelta
from decimal import Decimal

from sqlalchemy import func, select

from app.db.models.cost_ledger import CostLedger
from app.repositories.base import BaseRepository


class CostLedgerRepo(BaseRepository[CostLedger]):
    model = CostLedger

    async def sum_cost(
        self,
        organization_id: uuid.UUID | None = None,
        project_id: uuid.UUID | None = None,
        user_id: uuid.UUID | None = None,
        date_from: date | datetime | None = None,
        date_to: date | datetime | None = None,
    ) -> Decimal:
        stmt = select(func.coalesce(func.sum(CostLedger.cost_usd), 0))
        if organization_id is not None:
            stmt = stmt.where(CostLedger.organization_id == organization_id)
        if project_id is not None:
            stmt = stmt.where(CostLedger.project_id == project_id)
        if user_id is not None:
            stmt = stmt.where(CostLedger.user_id == user_id)
        if date_from is not None:
            stmt = stmt.where(CostLedger.created_at >= date_from)
        if date_to is not None:
            # A bare `date` (as opposed to a `datetime`) means "through the end of that
            # calendar day". Comparing a timestamptz column against a bare date with `<=`
            # casts it to midnight of that day, silently excluding the whole day itself --
            # use an exclusive bound at the start of the next day instead.
            if isinstance(date_to, datetime):
                stmt = stmt.where(CostLedger.created_at <= date_to)
            else:
                stmt = stmt.where(CostLedger.created_at < date_to + timedelta(days=1))
        result = await self.db.execute(stmt)
        return result.scalar_one()
