import uuid

from fastapi import APIRouter, Depends

from app.api.deps import get_provider_config_repo, require_roles
from app.core.exceptions import NotFoundError
from app.core.logging import get_logger, log_method
from app.db.models.enums import UserRole
from app.db.models.provider_config import ProviderConfig
from app.db.models.user import User
from app.repositories.provider_config_repo import ProviderConfigRepo
from app.schemas.provider_config import ProviderConfigCreate, ProviderConfigOut, ProviderConfigUpdate

logger = get_logger(__name__)

router = APIRouter(prefix="/v1/provider-configs", tags=["provider_configs"])


@router.get("", response_model=list[ProviderConfigOut])
@log_method(logger)
async def list_provider_configs(
    user: User = Depends(require_roles(UserRole.admin)), repo: ProviderConfigRepo = Depends(get_provider_config_repo)
) -> list[ProviderConfigOut]:
    configs = await repo.list()
    logger.info("listing provider configs", user_id=user.id, count=len(configs))
    return [ProviderConfigOut.model_validate(p) for p in configs]


@router.post("", response_model=ProviderConfigOut, status_code=201)
@log_method(logger)
async def create_provider_config(
    body: ProviderConfigCreate,
    user: User = Depends(require_roles(UserRole.admin)),
    repo: ProviderConfigRepo = Depends(get_provider_config_repo),
) -> ProviderConfigOut:
    logger.info("creating provider config", user_id=user.id, provider=body.provider, enabled=body.enabled)
    config = await repo.add(
        ProviderConfig(
            provider=body.provider, display_name=body.display_name, credential_ref=body.credential_ref, enabled=body.enabled
        )
    )
    logger.info("provider_config_created", provider_config_id=str(config.id), provider=config.provider, enabled=config.enabled)
    return ProviderConfigOut.model_validate(config)


@router.patch("/{provider_config_id}", response_model=ProviderConfigOut)
@log_method(logger)
async def update_provider_config(
    provider_config_id: uuid.UUID,
    body: ProviderConfigUpdate,
    user: User = Depends(require_roles(UserRole.admin)),
    repo: ProviderConfigRepo = Depends(get_provider_config_repo),
) -> ProviderConfigOut:
    logger.info("updating provider config", user_id=user.id, provider_config_id=str(provider_config_id), fields=list(body.model_dump(exclude_none=True).keys()))
    config = await repo.get(provider_config_id)
    if config is None:
        raise NotFoundError("Provider config not found")
    if body.display_name is not None:
        config.display_name = body.display_name
    if body.credential_ref is not None:
        config.credential_ref = body.credential_ref
    if body.enabled is not None:
        config.enabled = body.enabled
    await repo.db.flush()
    await repo.db.refresh(config)
    logger.info("provider_config_updated", provider_config_id=str(provider_config_id), enabled=config.enabled)
    return ProviderConfigOut.model_validate(config)

@log_method(logger)
@router.delete("/{provider_config_id}", status_code=204)
async def delete_provider_config(
    provider_config_id: uuid.UUID,
    user: User = Depends(require_roles(UserRole.admin)),
    repo: ProviderConfigRepo = Depends(get_provider_config_repo),
) -> None:
    config = await repo.get(provider_config_id)
    if config is None:
        raise NotFoundError("Provider config not found")
    await repo.delete(config)
    logger.info("provider_config_deleted", provider_config_id=str(provider_config_id), provider=config.provider)
