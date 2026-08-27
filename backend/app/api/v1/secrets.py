from fastapi import APIRouter, BackgroundTasks, Depends

from app.api.deps import get_secret_audit_log_repo, get_secret_service, require_roles
from app.core.config import Settings, get_settings
from app.core.logging import get_logger
from app.db.models.enums import SecretAuditStatus, SecretOperation, UserRole
from app.db.models.user import User
from app.repositories.secret_audit_log_repo import SecretAuditLogRepo
from app.schemas.secret import (
    PaginatedSecretAuditLog,
    SecretAuditLogOut,
    SecretProviderConfigOut,
    SecretProviderInfo,
    SecretRotateRequest,
    SecretRotateResponse,
    SecretStatusOut,
)
from app.secrets.factory import list_provider_metadata
from app.secrets.service import SecretService
from app.services.logging_service import record_secret_audit

router = APIRouter(prefix="/admin/secrets", tags=["secrets"])
logger = get_logger(__name__)

# (display label, underlying secret name(s) that must ALL resolve for this
# provider to be considered "configured"). AWS Bedrock needs a key pair; every
# other LLM provider here needs exactly one secret.
_LLM_CREDENTIAL_CHECKS: list[tuple[str, list[str]]] = [
    ("OPENAI", ["OPENAI_API_KEY"]),
    ("ANTHROPIC", ["ANTHROPIC_API_KEY"]),
    ("GOOGLE_GEMINI", ["GOOGLE_API_KEY"]),
    ("AWS_BEDROCK", ["AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY"]),
    ("AZURE_OPENAI", ["AZURE_OPENAI_KEY"]),
]


@router.get("/providers", response_model=SecretProviderConfigOut)
async def get_secret_providers(
    user: User = Depends(require_roles(UserRole.admin)),
    settings: Settings = Depends(get_settings),
) -> SecretProviderConfigOut:
    """Which SecretProvider backend is active, and which others this deployment
    is configured for. Selecting the active provider is a deployment-time
    decision (SECRET_PROVIDER env var + restart) -- not something this endpoint
    can change live, since swapping backends mid-process would leave any
    already-cached secret values pointing at the wrong source."""
    logger.info("listing secret providers", active_provider=settings.secret_provider, admin_user_id=user.id)
    providers = [SecretProviderInfo(**info) for info in list_provider_metadata(settings)]
    logger.info("secret providers resolved", provider_count=len(providers), active_provider=settings.secret_provider)
    return SecretProviderConfigOut(
        active_provider=settings.secret_provider,
        providers=providers,
    )


@router.get("/status", response_model=list[SecretStatusOut])
async def get_secret_status(
    background_tasks: BackgroundTasks,
    user: User = Depends(require_roles(UserRole.admin)),
    secret_service: SecretService = Depends(get_secret_service),
    settings: Settings = Depends(get_settings),
) -> list[SecretStatusOut]:
    """Never returns a secret value -- only whether each LLM provider's
    credential(s) currently resolve. Each underlying check is audit-logged."""
    logger.info("checking LLM secret status", admin_user_id=user.id, provider=settings.secret_provider)
    results: list[SecretStatusOut] = []
    for label, secret_names in _LLM_CREDENTIAL_CHECKS:
        audit_status = SecretAuditStatus.success
        try:
            values = [await secret_service.get_secret(name) for name in secret_names]
            status = "configured" if all(values) else "not_configured"
            logger.info(
                "secret check completed",
                provider=label,
                secret_names=secret_names,
                status=status,
                configured=all(values),
            )
        except Exception:
            status = "error"
            audit_status = SecretAuditStatus.error
            logger.exception(
                "secret status check failed",
                provider=label,
                secret_names=secret_names,
                admin_user_id=user.id,
            )
        results.append(SecretStatusOut(provider=label, status=status))
        for name in secret_names:
            background_tasks.add_task(
                record_secret_audit,
                tenant_id=None,
                operation=SecretOperation.get,
                provider=settings.secret_provider,
                secret_name=name,
                user_id=user.id,
                status=audit_status,
            )
    return results


@router.post("/rotate", response_model=SecretRotateResponse)
async def rotate_secret(
    body: SecretRotateRequest,
    background_tasks: BackgroundTasks,
    user: User = Depends(require_roles(UserRole.admin)),
    secret_service: SecretService = Depends(get_secret_service),
    settings: Settings = Depends(get_settings),
) -> SecretRotateResponse:
    """Manual rotation support: invalidates the cached value and re-fetches from
    the provider (force_refresh=True), so a secret rotated in Infisical/AWS/GCP/
    Azure/Vault takes effect immediately instead of waiting out the cache TTL."""
    logger.info(
        "rotating secret",
        secret_name=body.secret_name,
        tenant=body.tenant,
        admin_user_id=user.id,
        provider=settings.secret_provider,
    )
    audit_status = SecretAuditStatus.success
    try:
        value = await secret_service.get_secret(body.secret_name, tenant=body.tenant, force_refresh=True)
        status: str = "rotated" if value is not None else "error"
        if value is None:
            audit_status = SecretAuditStatus.error
            logger.warning(
                "secret rotation returned no value",
                secret_name=body.secret_name,
                tenant=body.tenant,
                provider=settings.secret_provider,
            )
        else:
            logger.info("secret rotation succeeded", secret_name=body.secret_name, tenant=body.tenant)
    except Exception:
        status = "error"
        audit_status = SecretAuditStatus.error
        logger.exception(
            "secret rotation failed",
            secret_name=body.secret_name,
            tenant=body.tenant,
            admin_user_id=user.id,
            provider=settings.secret_provider,
        )

    background_tasks.add_task(
        record_secret_audit,
        tenant_id=body.tenant,
        operation=SecretOperation.rotate,
        provider=settings.secret_provider,
        secret_name=body.secret_name,
        user_id=user.id,
        status=audit_status,
    )
    return SecretRotateResponse(secret_name=body.secret_name, provider=settings.secret_provider, status=status)


@router.get("/audit-log", response_model=PaginatedSecretAuditLog)
async def get_secret_audit_log(
    page: int = 1,
    page_size: int = 25,
    user: User = Depends(require_roles(UserRole.admin)),
    repo: SecretAuditLogRepo = Depends(get_secret_audit_log_repo),
) -> PaginatedSecretAuditLog:
    logger.info("loading secret audit log", page=page, page_size=page_size, admin_user_id=user.id)
    items, total = await repo.list_paginated(page=page, page_size=min(page_size, 100))
    logger.info("secret audit log loaded", page=page, item_count=len(items), total=total)
    return PaginatedSecretAuditLog(
        items=[SecretAuditLogOut.model_validate(item) for item in items], page=page, page_size=page_size, total=total
    )
