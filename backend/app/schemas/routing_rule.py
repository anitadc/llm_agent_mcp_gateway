import uuid
from datetime import datetime

from pydantic import BaseModel

from app.db.models.enums import ModelCapability, ProviderNameEnum, RoutingStrategy


class RoutingRuleTarget(BaseModel):
    provider: ProviderNameEnum
    model: str
    weight: int | None = None


class RoutingRuleCreate(BaseModel):
    model_alias: str
    project_id: uuid.UUID | None = None
    user_id: str | None = None
    capability: ModelCapability = ModelCapability.chat
    strategy: RoutingStrategy
    targets: list[RoutingRuleTarget]
    priority: int = 0
    is_active: bool = True


class RoutingRuleUpdate(BaseModel):
    strategy: RoutingStrategy | None = None
    targets: list[RoutingRuleTarget] | None = None
    priority: int | None = None
    is_active: bool | None = None


class RoutingRuleOut(RoutingRuleCreate):
    id: uuid.UUID
    created_at: datetime

    model_config = {"from_attributes": True}
