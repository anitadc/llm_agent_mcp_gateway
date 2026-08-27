from fastapi import APIRouter, Depends

from app.api.deps import get_current_identity, get_current_user
from app.core.logging import get_logger
from app.db.models.user import User
from app.identity.models import UserIdentity
from app.schemas.auth import SessionInfo

router = APIRouter(prefix="/v1/auth", tags=["auth"])
logger = get_logger(__name__)


@router.post("/token/exchange", response_model=SessionInfo)
async def exchange_token(
    user: User = Depends(get_current_user), identity: UserIdentity = Depends(get_current_identity)
) -> SessionInfo:
    logger.info("exchanging identity token", user_id=user.id, identity_provider=identity.provider)
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
