import uuid
from datetime import date

from pydantic import BaseModel


class ModelBreakdown(BaseModel):
    model_alias: str
    resolved_provider: str | None = None
    resolved_model: str | None = None
    requests: int
    cost_usd: float


class UsageSummary(BaseModel):
    organization_id: uuid.UUID | None = None
    project_id: uuid.UUID | None = None
    date_from: date
    date_to: date
    total_cost_usd: float
    total_requests: int
    total_prompt_tokens: int
    total_completion_tokens: int
    cache_hit_rate: float
    breakdown_by_model: list[ModelBreakdown]
