from sqlalchemy import select

from app.db.models.model_pricing import ModelPricing
from app.repositories.base import BaseRepository


class ModelPricingRepo(BaseRepository[ModelPricing]):
    model = ModelPricing

    async def get_by_provider_model(self, provider: str, model: str) -> ModelPricing | None:
        result = await self.db.execute(
            select(ModelPricing).where(ModelPricing.provider == provider, ModelPricing.model == model)
        )
        return result.scalar_one_or_none()
