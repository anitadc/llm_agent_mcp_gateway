import uuid

from pydantic import BaseModel, Field, model_validator

from app.db.models.enums import BudgetPeriod


class BudgetCreate(BaseModel):
    organization_id: uuid.UUID | None = None
    project_id: uuid.UUID | None = None
    user_id: uuid.UUID | None = None
    period: BudgetPeriod = BudgetPeriod.monthly
    limit_usd: float
    alert_threshold_pct: int = Field(default=80, ge=1, le=100)

    @model_validator(mode="after")
    def require_one_scope(self) -> "BudgetCreate":
        if not (self.organization_id or self.project_id or self.user_id):
            raise ValueError("One of organization_id, project_id, or user_id is required")
        return self


class BudgetUpdate(BaseModel):
    period: BudgetPeriod | None = None
    limit_usd: float | None = None
    alert_threshold_pct: int | None = Field(default=None, ge=1, le=100)


class BudgetOut(BaseModel):
    id: uuid.UUID
    organization_id: uuid.UUID | None = None
    project_id: uuid.UUID | None = None
    user_id: uuid.UUID | None = None
    period: BudgetPeriod
    limit_usd: float
    alert_threshold_pct: int
    current_spend_usd: float
    percent_used: float

    model_config = {"from_attributes": True}
