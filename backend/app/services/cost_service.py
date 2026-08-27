from decimal import Decimal

from app.repositories.model_pricing_repo import ModelPricingRepo


class CostService:
    """Reads per-model USD pricing from the model_pricing table (admin-editable via
    /v1/model-pricing) rather than a hardcoded table, so pricing changes and new
    models don't require a code change + redeploy."""

    def __init__(self, pricing_repo: ModelPricingRepo) -> None:
        self.pricing_repo = pricing_repo

    async def calculate(self, prompt_tokens: int, completion_tokens: int, provider: str | None, model: str | None) -> Decimal:
        if not provider or not model:
            return Decimal("0")
        entry = await self.pricing_repo.get_by_provider_model(provider, model)
        if entry is None:
            return Decimal("0")
        prompt_cost = (Decimal(prompt_tokens) / 1000) * entry.prompt_per_1k
        completion_cost = (Decimal(completion_tokens) / 1000) * (entry.completion_per_1k or Decimal("0"))
        return prompt_cost + completion_cost
