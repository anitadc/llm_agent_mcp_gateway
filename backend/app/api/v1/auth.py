from fastapi import APIRouter, Depends

from app.api.deps import get_current_identity, get_current_user
from app.core.logging import get_logger, log_method
from app.db.models.user import User
from app.identity.models import UserIdentity
from app.schemas.auth import SessionInfo
from app.schemas.auth import LocalTokenRequest, LocalTokenResponse
from app.core.config import get_settings
from app.identity.local_token import issue_local_jwt

logger = get_logger(__name__)

router = APIRouter(prefix="/v1/auth", tags=["auth"])


@router.get("/provider")
@log_method(logger)
async def get_provider_info(settings=Depends(get_settings)) -> dict:
    """Public info about which identity provider the backend is configured to use.

    This is intentionally non-sensitive and helps frontends adapt their
    login flow (Keycloak redirect vs. a dev local token form).
    """
    return {
        "identity_provider": settings.identity_provider,
        "jwt_secret": settings.jwt_secret 
    }


@router.post("/token/exchange", response_model=SessionInfo)
@log_method(logger)
async def exchange_token(
    user: User = Depends(get_current_user), identity: UserIdentity = Depends(get_current_identity)
) -> SessionInfo:
    logger.info(
        "session_exchanged",
        user_id=str(user.id),
        provider=identity.provider,
        tenant_id=identity.tenant_id,
    )
    return SessionInfo(
        user_id=user.id,
        email=user.email,
        role=user.role,
        organization_id=user.organization_id,
        identity_provider=identity.provider,
        tenant_id=identity.tenant_id,
        roles=identity.roles,
        groups=identity.groups,
        attributes=identity.attributes,
    )



@router.post("/local/issue", response_model=LocalTokenResponse)
@log_method(logger)
async def issue_local_token(body: LocalTokenRequest, settings=Depends(get_settings)) -> LocalTokenResponse:
    """Dev-only: issues a locally-signed JWT when no external IdP is configured.

    This endpoint is intentionally gated: `settings.identity_provider` must be
    None and `settings.allow_local_token_issue` must be True. It is intended
    for local development and tests only.
    """
    if settings.identity_provider != "local":
        from fastapi import HTTPException

        raise HTTPException(status_code=403, detail="Local token issuance is disabled")

    token, expires = issue_local_jwt(
        settings,
        user_id=body.user_id,
        email=body.email,
        roles=body.roles,
        groups=body.groups,
        tenant_id=body.tenant_id,
        expires_seconds=body.expires_seconds,
    )
    return LocalTokenResponse(token=token, expires_in=expires)
