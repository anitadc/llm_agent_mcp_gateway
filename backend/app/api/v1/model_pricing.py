import uuid

from fastapi import APIRouter, Depends

from app.api.deps import get_model_pricing_repo, require_roles
from app.core.exceptions import NotFoundError
from app.core.logging import get_logger
from app.db.models.enums import UserRole
from app.db.models.model_pricing import ModelPricing
from app.db.models.user import User
from app.repositories.model_pricing_repo import ModelPricingRepo
from app.schemas.model_pricing import ModelPricingCreate, ModelPricingOut, ModelPricingUpdate

logger = get_logger(__name__)

router = APIRouter(prefix="/v1/model-pricing", tags=["model_pricing"])


@router.get("", response_model=list[ModelPricingOut])
async def list_model_pricing(
    user: User = Depends(require_roles(UserRole.admin)), repo: ModelPricingRepo = Depends(get_model_pricing_repo)
) -> list[ModelPricingOut]:
    return [ModelPricingOut.model_validate(p) for p in await repo.list()]


@router.post("", response_model=ModelPricingOut, status_code=201)
async def create_model_pricing(
    body: ModelPricingCreate,
    user: User = Depends(require_roles(UserRole.admin)),
    repo: ModelPricingRepo = Depends(get_model_pricing_repo),
) -> ModelPricingOut:
    entry = await repo.add(
        ModelPricing(
            provider=body.provider,
            model=body.model,
            prompt_per_1k=body.prompt_per_1k,
            completion_per_1k=body.completion_per_1k,
        )
    )
    logger.info("model_pricing_created", pricing_id=str(entry.id), provider=entry.provider, model=entry.model)
    return ModelPricingOut.model_validate(entry)


@router.patch("/{pricing_id}", response_model=ModelPricingOut)
async def update_model_pricing(
    pricing_id: uuid.UUID,
    body: ModelPricingUpdate,
    user: User = Depends(require_roles(UserRole.admin)),
    repo: ModelPricingRepo = Depends(get_model_pricing_repo),
) -> ModelPricingOut:
    entry = await repo.get(pricing_id)
    if entry is None:
        raise NotFoundError("Pricing entry not found")
    if body.prompt_per_1k is not None:
        entry.prompt_per_1k = body.prompt_per_1k
    if body.completion_per_1k is not None:
        entry.completion_per_1k = body.completion_per_1k
    await repo.db.flush()
    await repo.db.refresh(entry)
    logger.info("model_pricing_updated", pricing_id=str(pricing_id))
    return ModelPricingOut.model_validate(entry)


@router.delete("/{pricing_id}", status_code=204)
async def delete_model_pricing(
    pricing_id: uuid.UUID,
    user: User = Depends(require_roles(UserRole.admin)),
    repo: ModelPricingRepo = Depends(get_model_pricing_repo),
) -> None:
    entry = await repo.get(pricing_id)
    if entry is None:
        raise NotFoundError("Pricing entry not found")
    await repo.delete(entry)
    logger.info("model_pricing_deleted", pricing_id=str(pricing_id))
