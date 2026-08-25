import uuid

from fastapi import APIRouter, Depends

from app.api.deps import require_roles, get_user_repo
from app.core.exceptions import NotFoundError
from app.core.logging import get_logger
from app.db.models.enums import UserRole
from app.db.models.user import User
from app.repositories.user_repo import UserRepo
from app.schemas.user import UserCreate, UserOut, UserUpdate

logger = get_logger(__name__)

router = APIRouter(prefix="/v1/users", tags=["users"])


@router.get("", response_model=list[UserOut])
async def list_users(
    organization_id: uuid.UUID | None = None,
    user: User = Depends(require_roles(UserRole.admin)),
    repo: UserRepo = Depends(get_user_repo),
) -> list[UserOut]:
    return [UserOut.model_validate(u) for u in await repo.list_visible(organization_id)]


@router.post("", response_model=UserOut, status_code=201)
async def create_user(
    body: UserCreate,
    user: User = Depends(require_roles(UserRole.admin)),
    repo: UserRepo = Depends(get_user_repo),
) -> UserOut:
    new_user = await repo.add(User(email=body.email, role=body.role, organization_id=body.organization_id))
    logger.info("user_created", user_id=str(new_user.id), role=new_user.role.value)
    return UserOut.model_validate(new_user)


@router.patch("/{user_id}", response_model=UserOut)
async def update_user(
    user_id: uuid.UUID,
    body: UserUpdate,
    user: User = Depends(require_roles(UserRole.admin)),
    repo: UserRepo = Depends(get_user_repo),
) -> UserOut:
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
