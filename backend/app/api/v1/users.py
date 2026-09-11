import uuid
from fastapi import APIRouter, Depends, HTTPException, status

from app.api.deps import require_roles, get_user_repo
from app.core.exceptions import NotFoundError
from app.core.logging import get_logger, log_method
from app.db.models.enums import UserRole
from app.db.models.user import User
from app.repositories.user_repo import UserRepo
from app.schemas.user import UserCreate, UserOut, UserUpdate

from app.api.v1.keycloak import Keycloak
from app.core.config import get_settings

logger = get_logger(__name__)

router = APIRouter(prefix="/v1/users", tags=["users"])

settings = get_settings()
IDENTITY_PROVIDER = settings.identity_provider

@router.get("", response_model=list[UserOut])
@log_method(logger)
async def list_users(
    organization_id: uuid.UUID | None = None,
    user: User = Depends(require_roles(UserRole.admin)),
    repo: UserRepo = Depends(get_user_repo),
) -> list[UserOut]:
    users = await repo.list_visible(organization_id)
    logger.info("listing users", admin_user_id=user.id, organization_id=str(organization_id) if organization_id else None, count=len(users))
    return [UserOut.model_validate(u) for u in users]


@router.post("", response_model=UserOut, status_code=201)
@log_method(logger)
async def create_user(
    body: UserCreate,
    user: User = Depends(require_roles(UserRole.admin)),
    repo: UserRepo = Depends(get_user_repo),
) -> UserOut:
    logger.info("creating user", admin_user_id=user.id, email=body.email, role=body.role.value, organization_id=str(body.organization_id) if body.organization_id else None)
    new_user = await repo.add(User(email=body.email, role=body.role, organization_id=body.organization_id))
    logger.info("user_created", user_id=str(new_user.id), role=new_user.role.value)

    if IDENTITY_PROVIDER == "keycloak":
        try:
            admin_token = await Keycloak.get_keycloak_admin_token()
            await Keycloak.create_keycloak_user(admin_token=admin_token, body=body)
        except Exception as exc:
            logger.error("keycloak_connection_error", error=str(exc))
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="User saved to database, but Keycloak server was unreachable.",
            )

    return UserOut.model_validate(new_user)


@router.patch("/{user_id}", response_model=UserOut)
@log_method(logger)
async def update_user(
    user_id: uuid.UUID,
    body: UserUpdate,
    user: User = Depends(require_roles(UserRole.admin)),
    repo: UserRepo = Depends(get_user_repo),
) -> UserOut:
    logger.info("updating user", admin_user_id=user.id, user_id=str(user_id), fields=list(body.model_dump(exclude_none=True).keys()))
    target = await repo.get(user_id)
    if target is None:
        raise NotFoundError("User not found")
    if body.role is not None:
        target.role = body.role
    if body.organization_id is not None:
        target.organization_id = body.organization_id
    await repo.db.flush()
    await repo.db.refresh(target)
    logger.info("user_updated", user_id=str(user_id), role=target.role.value)
    return UserOut.model_validate(target)