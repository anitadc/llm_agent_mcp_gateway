from app.core.logging import log_method, get_logger
from sqlalchemy import select

from app.db.models.model_pricing import ModelPricing
from app.repositories.base import BaseRepository
logger = get_logger(__name__)

class ModelPricingRepo(BaseRepository[ModelPricing]):
    model = ModelPricing

    @log_method(logger)
    async def get_by_provider_model(self, provider: str, model: str) -> ModelPricing | None:
        result = await self.db.execute(
            select(ModelPricing).where(ModelPricing.provider == provider, ModelPricing.model == model)
        )
        return result.scalar_one_or_none()
