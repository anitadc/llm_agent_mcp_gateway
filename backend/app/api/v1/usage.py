import uuid
from datetime import date, datetime, timedelta, timezone

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_cost_ledger_repo, get_current_user, get_db
from app.core.logging import get_logger, log_method
from app.db.models.cost_ledger import CostLedger
from app.db.models.request_log import RequestLog
from app.db.models.user import User
from app.repositories.cost_ledger_repo import CostLedgerRepo
from app.schemas.usage import ModelBreakdown, UsageSummary

router = APIRouter(prefix="/v1/usage", tags=["usage"])
logger = get_logger(__name__)


@router.get("/summary", response_model=UsageSummary)
@log_method(logger)
async def get_usage_summary(
    organization_id: uuid.UUID | None = None,
    project_id: uuid.UUID | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
    user: User = Depends(get_current_user),
    cost_ledger_repo: CostLedgerRepo = Depends(get_cost_ledger_repo),
    db: AsyncSession = Depends(get_db),
) -> UsageSummary:
    logger.info(
        "loading usage summary",
        user_id=user.id,
        organization_id=str(organization_id) if organization_id else None,
        project_id=str(project_id) if project_id else None,
        date_from=date_from.isoformat() if date_from else None,
        date_to=date_to.isoformat() if date_to else None,
    )
    resolved_from = date_from or (datetime.now(timezone.utc).date() - timedelta(days=30))
    resolved_to = date_to or datetime.now(timezone.utc).date()
    # resolved_to is a calendar date; comparing a timestamptz column against it directly
    # would cast to midnight of that day and exclude everything from "today" that
    # happened after 00:00 UTC. Use the start of the *next* day as an exclusive bound instead.
    exclusive_upper_bound = resolved_to + timedelta(days=1)

    total_cost = await cost_ledger_repo.sum_cost(
        organization_id=organization_id, project_id=project_id, date_from=resolved_from, date_to=resolved_to
    )

    log_stmt = select(
        func.count(RequestLog.id),
        func.coalesce(func.sum(RequestLog.prompt_tokens), 0),
        func.coalesce(func.sum(RequestLog.completion_tokens), 0),
    )
    if organization_id is not None:
        log_stmt = log_stmt.where(RequestLog.organization_id == organization_id)
    if project_id is not None:
        log_stmt = log_stmt.where(RequestLog.project_id == project_id)
    log_stmt = log_stmt.where(RequestLog.created_at >= resolved_from).where(
        RequestLog.created_at < exclusive_upper_bound
    )
    total_requests, total_prompt_tokens, total_completion_tokens = (await db.execute(log_stmt)).one()

    cache_hits_stmt = select(func.count()).select_from(RequestLog).where(RequestLog.cache_hit.is_(True))
    if organization_id is not None:
        cache_hits_stmt = cache_hits_stmt.where(RequestLog.organization_id == organization_id)
    if project_id is not None:
        cache_hits_stmt = cache_hits_stmt.where(RequestLog.project_id == project_id)
    cache_hits_stmt = cache_hits_stmt.where(RequestLog.created_at >= resolved_from).where(
        RequestLog.created_at < exclusive_upper_bound
    )
    cache_hits = (await db.execute(cache_hits_stmt)).scalar_one()
    cache_hit_rate = (cache_hits / total_requests) if total_requests else 0.0

    breakdown_stmt = (
        select(
            RequestLog.model_alias,
            RequestLog.resolved_provider,
            RequestLog.resolved_model,
            func.count(RequestLog.id),
            func.coalesce(func.sum(CostLedger.cost_usd), 0),
        )
        .join(CostLedger, CostLedger.request_log_id == RequestLog.id, isouter=True)
        .where(RequestLog.created_at >= resolved_from)
        .where(RequestLog.created_at < exclusive_upper_bound)
        .group_by(RequestLog.model_alias, RequestLog.resolved_provider, RequestLog.resolved_model)
    )
    if organization_id is not None:
        breakdown_stmt = breakdown_stmt.where(RequestLog.organization_id == organization_id)
    if project_id is not None:
        breakdown_stmt = breakdown_stmt.where(RequestLog.project_id == project_id)
    breakdown_rows = (await db.execute(breakdown_stmt)).all()

    return UsageSummary(
        organization_id=organization_id,
        project_id=project_id,
        date_from=resolved_from,
        date_to=resolved_to,
        total_cost_usd=float(total_cost),
        total_requests=total_requests,
        total_prompt_tokens=total_prompt_tokens,
        total_completion_tokens=total_completion_tokens,
        cache_hit_rate=cache_hit_rate,
        breakdown_by_model=[
            ModelBreakdown(
                model_alias=row[0], resolved_provider=row[1], resolved_model=row[2], requests=row[3], cost_usd=float(row[4])
            )
            for row in breakdown_rows
        ],
    )
