import uuid

from fastapi import APIRouter, Depends

from app.api.deps import get_provider_config_repo, require_roles
from app.core.exceptions import NotFoundError
from app.db.models.enums import UserRole
from app.db.models.provider_config import ProviderConfig
from app.db.models.user import User
from app.repositories.provider_config_repo import ProviderConfigRepo
from app.schemas.provider_config import ProviderConfigCreate, ProviderConfigOut, ProviderConfigUpdate

router = APIRouter(prefix="/v1/provider-configs", tags=["provider_configs"])


@router.get("", response_model=list[ProviderConfigOut])
async def list_provider_configs(
    user: User = Depends(require_roles(UserRole.admin)), repo: ProviderConfigRepo = Depends(get_provider_config_repo)
) -> list[ProviderConfigOut]:
    return [ProviderConfigOut.model_validate(p) for p in await repo.list()]


@router.post("", response_model=ProviderConfigOut, status_code=201)
async def create_provider_config(
    body: ProviderConfigCreate,
    user: User = Depends(require_roles(UserRole.admin)),
    repo: ProviderConfigRepo = Depends(get_provider_config_repo),
) -> ProviderConfigOut:
    config = await repo.add(
        ProviderConfig(
            provider=body.provider, display_name=body.display_name, credential_ref=body.credential_ref, enabled=body.enabled
        )
    )
    return ProviderConfigOut.model_validate(config)


@router.patch("/{provider_config_id}", response_model=ProviderConfigOut)
async def update_provider_config(
    provider_config_id: uuid.UUID,
    body: ProviderConfigUpdate,
    user: User = Depends(require_roles(UserRole.admin)),
    repo: ProviderConfigRepo = Depends(get_provider_config_repo),
) -> ProviderConfigOut:
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
    return ProviderConfigOut.model_validate(config)
