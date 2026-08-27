import uuid

from fastapi import APIRouter, Depends

from app.api.deps import get_access_policy_repo, get_tenant_identity_config_repo, require_roles
from app.core.config import Settings, get_settings
from app.core.exceptions import NotFoundError
from app.core.logging import get_logger
from app.db.models.access_policy import AccessPolicy
from app.db.models.enums import UserRole
from app.db.models.tenant_identity_config import TenantIdentityConfig
from app.db.models.user import User
from app.identity.factory import list_provider_metadata
from app.repositories.access_policy_repo import AccessPolicyRepo
from app.repositories.tenant_identity_config_repo import TenantIdentityConfigRepo
from app.schemas.identity import (
    AccessPolicyCreate,
    AccessPolicyOut,
    AccessPolicyUpdate,
    IdentityProviderConfigOut,
    IdentityProviderInfo,
    TenantIdentityConfigCreate,
    TenantIdentityConfigOut,
    TenantIdentityConfigUpdate,
)

router = APIRouter(prefix="/admin/identity", tags=["identity"])
logger = get_logger(__name__)


@router.get("/providers", response_model=IdentityProviderConfigOut)
async def get_identity_providers(
    user: User = Depends(require_roles(UserRole.admin)),
    settings: Settings = Depends(get_settings),
) -> IdentityProviderConfigOut:
    """Which IdentityProvider is the process-wide default, and which others
    this deployment is configured for. Like the Secret Provider layer, the
    active default is a deployment-time decision (IDENTITY_PROVIDER env var +
    restart) -- per-tenant overrides are managed via /tenant-configs instead of
    switching this default live."""
    logger.info("listing identity providers", admin_user_id=user.id, active_provider=settings.identity_provider)
    return IdentityProviderConfigOut(
        active_provider=settings.identity_provider,
        providers=[IdentityProviderInfo(**info) for info in list_provider_metadata(settings)],
    )


@router.get("/tenant-configs", response_model=list[TenantIdentityConfigOut])
async def list_tenant_configs(
    user: User = Depends(require_roles(UserRole.admin)),
    repo: TenantIdentityConfigRepo = Depends(get_tenant_identity_config_repo),
) -> list[TenantIdentityConfigOut]:
    configs = await repo.list()
    logger.info("listing tenant identity configs", admin_user_id=user.id, count=len(configs))
    return [TenantIdentityConfigOut.model_validate(c) for c in configs]


@router.post("/tenant-configs", response_model=TenantIdentityConfigOut, status_code=201)
async def create_tenant_config(
    body: TenantIdentityConfigCreate,
    user: User = Depends(require_roles(UserRole.admin)),
    repo: TenantIdentityConfigRepo = Depends(get_tenant_identity_config_repo),
) -> TenantIdentityConfigOut:
    logger.info("creating tenant identity config", admin_user_id=user.id, tenant_id=str(body.tenant_id), provider=body.provider)
    config = await repo.add(
        TenantIdentityConfig(
            tenant_id=body.tenant_id, provider=body.provider, issuer=body.issuer, configuration=body.configuration
        )
    )
    return TenantIdentityConfigOut.model_validate(config)


@router.put("/tenant-configs/{config_id}", response_model=TenantIdentityConfigOut)
async def update_tenant_config(
    config_id: uuid.UUID,
    body: TenantIdentityConfigUpdate,
    user: User = Depends(require_roles(UserRole.admin)),
    repo: TenantIdentityConfigRepo = Depends(get_tenant_identity_config_repo),
) -> TenantIdentityConfigOut:
    logger.info("updating tenant identity config", admin_user_id=user.id, config_id=str(config_id), fields=list(body.model_dump(exclude_none=True).keys()))
    config = await repo.get(config_id)
    if config is None:
        raise NotFoundError("Tenant identity config not found")
    if body.provider is not None:
        config.provider = body.provider
    if body.issuer is not None:
        config.issuer = body.issuer
    if body.configuration is not None:
        config.configuration = body.configuration
    await repo.db.flush()
    await repo.db.refresh(config)
    return TenantIdentityConfigOut.model_validate(config)


@router.delete("/tenant-configs/{config_id}", status_code=204)
async def delete_tenant_config(
    config_id: uuid.UUID,
    user: User = Depends(require_roles(UserRole.admin)),
    repo: TenantIdentityConfigRepo = Depends(get_tenant_identity_config_repo),
) -> None:
    logger.info("deleting tenant identity config", admin_user_id=user.id, config_id=str(config_id))
    config = await repo.get(config_id)
    if config is None:
        raise NotFoundError("Tenant identity config not found")
    await repo.delete(config)


@router.get("/access-policies", response_model=list[AccessPolicyOut])
async def list_access_policies(
    user: User = Depends(require_roles(UserRole.admin)),
    repo: AccessPolicyRepo = Depends(get_access_policy_repo),
) -> list[AccessPolicyOut]:
    policies = await repo.list()
    logger.info("listing access policies", admin_user_id=user.id, count=len(policies))
    return [AccessPolicyOut.model_validate(p) for p in policies]


@router.post("/access-policies", response_model=AccessPolicyOut, status_code=201)
async def create_access_policy(
    body: AccessPolicyCreate,
    user: User = Depends(require_roles(UserRole.admin)),
    repo: AccessPolicyRepo = Depends(get_access_policy_repo),
) -> AccessPolicyOut:
    logger.info("creating access policy", admin_user_id=user.id, project_id=str(body.project_id), name=body.name, is_active=body.is_active)
    policy = await repo.add(
        AccessPolicy(
            project_id=body.project_id,
            name=body.name,
            allowed_roles=body.allowed_roles,
            allowed_identity_providers=body.allowed_identity_providers,
            allowed_tool_names=body.allowed_tool_names,
            allowed_agent_keys=body.allowed_agent_keys,
            max_tokens=body.max_tokens,
            is_active=body.is_active,
        )
    )
    return AccessPolicyOut.model_validate(policy)


@router.patch("/access-policies/{policy_id}", response_model=AccessPolicyOut)
async def update_access_policy(
    policy_id: uuid.UUID,
    body: AccessPolicyUpdate,
    user: User = Depends(require_roles(UserRole.admin)),
    repo: AccessPolicyRepo = Depends(get_access_policy_repo),
) -> AccessPolicyOut:
    logger.info("updating access policy", admin_user_id=user.id, policy_id=str(policy_id), fields=list(body.model_dump(exclude_none=True).keys()))
    policy = await repo.get(policy_id)
    if policy is None:
        raise NotFoundError("Access policy not found")
    if body.allowed_roles is not None:
        policy.allowed_roles = body.allowed_roles
    if body.allowed_identity_providers is not None:
        policy.allowed_identity_providers = body.allowed_identity_providers
    if body.allowed_tool_names is not None:
        policy.allowed_tool_names = body.allowed_tool_names
    if body.allowed_agent_keys is not None:
        policy.allowed_agent_keys = body.allowed_agent_keys
    if body.max_tokens is not None:
        policy.max_tokens = body.max_tokens
    if body.is_active is not None:
        policy.is_active = body.is_active
    await repo.db.flush()
    await repo.db.refresh(policy)
    return AccessPolicyOut.model_validate(policy)


@router.delete("/access-policies/{policy_id}", status_code=204)
async def delete_access_policy(
    policy_id: uuid.UUID,
    user: User = Depends(require_roles(UserRole.admin)),
    repo: AccessPolicyRepo = Depends(get_access_policy_repo),
) -> None:
    logger.info("deleting access policy", admin_user_id=user.id, policy_id=str(policy_id))
    policy = await repo.get(policy_id)
    if policy is None:
        raise NotFoundError("Access policy not found")
    await repo.delete(policy)
