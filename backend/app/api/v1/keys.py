import uuid

from fastapi import APIRouter, Depends

from app.api.deps import get_api_key_repo, get_current_user, require_roles
from app.core.config import Settings, get_settings
from app.core.exceptions import NotFoundError
from app.core.logging import get_logger
from app.db.models.enums import UserRole
from app.db.models.user import User
from app.db.valkey import valkey_client
from app.repositories.api_key_repo import ApiKeyRepo
from app.repositories.user_repo import UserRepo
from app.schemas.api_key import ApiKeyCreate, ApiKeyOut
from app.services.auth_service import AuthService
from app.services.cache_service import CacheService

logger = get_logger(__name__)

router = APIRouter(prefix="/v1/keys", tags=["keys"])


@router.get("", response_model=list[ApiKeyOut])
async def list_keys(
    user: User = Depends(get_current_user), repo: ApiKeyRepo = Depends(get_api_key_repo)
) -> list[ApiKeyOut]:
    return [ApiKeyOut.model_validate(k) for k in await repo.list_visible()]


@router.post("", response_model=ApiKeyOut, status_code=201)
async def create_key(
    body: ApiKeyCreate,
    user: User = Depends(get_current_user),
    repo: ApiKeyRepo = Depends(get_api_key_repo),
    settings: Settings = Depends(get_settings),
) -> ApiKeyOut:
    auth_service = AuthService(repo, UserRepo(repo.db), CacheService(valkey_client), settings)
    api_key, raw_key = await auth_service.issue_api_key(body.name, body.project_id, body.scopes)
    logger.info("api_key_created", api_key_id=str(api_key.id), project_id=str(body.project_id))
    out = ApiKeyOut.model_validate(api_key)
    out.raw_key = raw_key
    return out


@router.delete("/{key_id}", status_code=204)
async def revoke_key(
    key_id: uuid.UUID,
    user: User = Depends(require_roles(UserRole.admin, UserRole.team_lead)),
    repo: ApiKeyRepo = Depends(get_api_key_repo),
    settings: Settings = Depends(get_settings),
) -> None:
    api_key = await repo.get(key_id)
    if api_key is None:
        raise NotFoundError("API key not found")
    auth_service = AuthService(repo, UserRepo(repo.db), CacheService(valkey_client), settings)
    await auth_service.revoke_api_key(api_key)
    logger.info("api_key_revoked", api_key_id=str(key_id))
