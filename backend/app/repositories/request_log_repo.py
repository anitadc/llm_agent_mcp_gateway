import uuid
from datetime import date, datetime, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.orm import selectinload

from app.db.models.enums import RequestStatus
from app.db.models.request_log import RequestLog
from app.repositories.base import BaseRepository


class RequestLogRepo(BaseRepository[RequestLog]):
    model = RequestLog

    async def get_by_request_id(self, request_id: uuid.UUID) -> RequestLog | None:
        stmt = (
            select(RequestLog)
            .options(selectinload(RequestLog.guardrail_results))
            .where(RequestLog.request_id == request_id)
        )
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

    async def list_paginated(
        self,
        organization_id: uuid.UUID | None = None,
        project_id: uuid.UUID | None = None,
        status: RequestStatus | None = None,
        model_alias: str | None = None,
        date_from: date | None = None,
        date_to: date | None = None,
        page: int = 1,
        page_size: int = 25,
    ) -> tuple[list[RequestLog], int]:
        stmt = select(RequestLog).options(selectinload(RequestLog.guardrail_results))
        count_stmt = select(func.count()).select_from(RequestLog)

        conditions = []
        if organization_id is not None:
            conditions.append(RequestLog.organization_id == organization_id)
        if project_id is not None:
            conditions.append(RequestLog.project_id == project_id)
        if status is not None:
            conditions.append(RequestLog.status == status)
        if model_alias is not None:
            conditions.append(RequestLog.model_alias == model_alias)
        if date_from is not None:
            conditions.append(RequestLog.created_at >= date_from)
        if date_to is not None:
            conditions.append(RequestLog.created_at <= date_to)

        for condition in conditions:
            stmt = stmt.where(condition)
            count_stmt = count_stmt.where(condition)

        stmt = stmt.order_by(RequestLog.created_at.desc()).offset((page - 1) * page_size).limit(page_size)

        total = (await self.db.execute(count_stmt)).scalar_one()
        items = list((await self.db.execute(stmt)).scalars().all())
        return items, total

    async def get_latency_p50_ms(
        self,
        provider: str,
        model: str,
        window_minutes: int = 30,
        min_samples: int = 3,
    ) -> float | None:
        """Rolling median (p50) latency for a resolved provider/model, computed from
        recent successful requests only. Returns None if there isn't enough recent
        data yet (min_samples), so callers can fall back sensibly for cold-start
        targets rather than routing on a single noisy sample."""
        cutoff = datetime.now(timezone.utc) - timedelta(minutes=window_minutes)
        stmt = select(
            func.percentile_cont(0.5).within_group(RequestLog.latency_ms),
            func.count(RequestLog.id),
        ).where(
            RequestLog.resolved_provider == provider,
            RequestLog.resolved_model == model,
            RequestLog.status == RequestStatus.success,
            RequestLog.created_at >= cutoff,
        )
        p50, sample_count = (await self.db.execute(stmt)).one()
        if p50 is None or sample_count < min_samples:
            return None
        return float(p50)
