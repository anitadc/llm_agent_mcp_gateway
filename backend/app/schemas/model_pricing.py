import uuid

from pydantic import BaseModel

from app.db.models.enums import ProviderNameEnum


class ModelPricingCreate(BaseModel):
    provider: ProviderNameEnum
    model: str
    prompt_per_1k: float
    completion_per_1k: float | None = None


class ModelPricingUpdate(BaseModel):
    prompt_per_1k: float | None = None
    completion_per_1k: float | None = None


class ModelPricingOut(BaseModel):
    id: uuid.UUID
    provider: ProviderNameEnum
    model: str
    prompt_per_1k: float
    completion_per_1k: float | None = None

    model_config = {"from_attributes": True}
