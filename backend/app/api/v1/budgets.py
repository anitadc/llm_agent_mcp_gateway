import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends

from app.api.deps import get_budget_repo, get_cost_ledger_repo, require_roles
from app.core.exceptions import NotFoundError
from app.core.logging import get_logger
from app.db.models.budget import Budget
from app.db.models.enums import BudgetPeriod, UserRole
from app.db.models.user import User
from app.repositories.budget_repo import BudgetRepo
from app.repositories.cost_ledger_repo import CostLedgerRepo
from app.schemas.budget import BudgetCreate, BudgetOut, BudgetUpdate

logger = get_logger(__name__)

router = APIRouter(prefix="/v1/budgets", tags=["budgets"])


def _period_start(period: BudgetPeriod) -> datetime:
    now = datetime.now(timezone.utc)
    if period == BudgetPeriod.daily:
        return datetime(now.year, now.month, now.day, tzinfo=timezone.utc)
    return datetime(now.year, now.month, 1, tzinfo=timezone.utc)


async def _to_out(budget: Budget, cost_ledger_repo: CostLedgerRepo) -> BudgetOut:
    spend = await cost_ledger_repo.sum_cost(
        organization_id=budget.organization_id,
        project_id=budget.project_id,
        user_id=budget.user_id,
        date_from=_period_start(budget.period),
    )
    limit_usd = float(budget.limit_usd)
    percent_used = float(spend) / limit_usd if limit_usd else 0.0
    return BudgetOut(
        id=budget.id,
        organization_id=budget.organization_id,
        project_id=budget.project_id,
        user_id=budget.user_id,
        period=budget.period,
        limit_usd=limit_usd,
        alert_threshold_pct=budget.alert_threshold_pct,
        current_spend_usd=float(spend),
        percent_used=percent_used,
    )


@router.get("", response_model=list[BudgetOut])
async def list_budgets(
    organization_id: uuid.UUID | None = None,
    project_id: uuid.UUID | None = None,
    user: User = Depends(require_roles(UserRole.admin, UserRole.team_lead)),
    repo: BudgetRepo = Depends(get_budget_repo),
    cost_ledger_repo: CostLedgerRepo = Depends(get_cost_ledger_repo),
) -> list[BudgetOut]:
    budgets = await repo.list_visible(organization_id, project_id)
    return [await _to_out(b, cost_ledger_repo) for b in budgets]


@router.post("", response_model=BudgetOut, status_code=201)
async def create_budget(
    body: BudgetCreate,
    user: User = Depends(require_roles(UserRole.admin, UserRole.team_lead)),
    repo: BudgetRepo = Depends(get_budget_repo),
    cost_ledger_repo: CostLedgerRepo = Depends(get_cost_ledger_repo),
) -> BudgetOut:
    budget = await repo.add(
        Budget(
            organization_id=body.organization_id,
            project_id=body.project_id,
            user_id=body.user_id,
            period=body.period,
            limit_usd=body.limit_usd,
            alert_threshold_pct=body.alert_threshold_pct,
        )
    )
    logger.info("budget_created", budget_id=str(budget.id), period=budget.period.value)
    return await _to_out(budget, cost_ledger_repo)


@router.patch("/{budget_id}", response_model=BudgetOut)
async def update_budget(
    budget_id: uuid.UUID,
    body: BudgetUpdate,
    user: User = Depends(require_roles(UserRole.admin, UserRole.team_lead)),
    repo: BudgetRepo = Depends(get_budget_repo),
    cost_ledger_repo: CostLedgerRepo = Depends(get_cost_ledger_repo),
) -> BudgetOut:
    budget = await repo.get(budget_id)
    if budget is None:
        raise NotFoundError("Budget not found")
    if body.period is not None:
        budget.period = body.period
    if body.limit_usd is not None:
        budget.limit_usd = body.limit_usd
    if body.alert_threshold_pct is not None:
        budget.alert_threshold_pct = body.alert_threshold_pct
    await repo.db.flush()
    await repo.db.refresh(budget)
    logger.info("budget_updated", budget_id=str(budget_id))
    return await _to_out(budget, cost_ledger_repo)


@router.delete("/{budget_id}", status_code=204)
async def delete_budget(
    budget_id: uuid.UUID,
    user: User = Depends(require_roles(UserRole.admin, UserRole.team_lead)),
    repo: BudgetRepo = Depends(get_budget_repo),
) -> None:
    budget = await repo.get(budget_id)
    if budget is None:
        raise NotFoundError("Budget not found")
    await repo.delete(budget)
    logger.info("budget_deleted", budget_id=str(budget_id))
