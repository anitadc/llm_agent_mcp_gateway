import uuid

from fastapi import APIRouter, Depends

from app.api.deps import get_current_user, get_project_user_repo, require_roles
from app.core.exceptions import NotFoundError
from app.db.models.enums import UserRole
from app.db.models.project_user import ProjectUser
from app.db.models.user import User
from app.repositories.project_user_repo import ProjectUserRepo
from app.schemas.project_user import ProjectUserCreate, ProjectUserOut, ProjectUserUpdate

router = APIRouter(prefix="/v1/project-users", tags=["project_users"])


@router.get("", response_model=list[ProjectUserOut])
async def list_project_users(
    project_id: uuid.UUID | None = None,
    user_id: uuid.UUID | None = None,
    user: User = Depends(get_current_user),
    repo: ProjectUserRepo = Depends(get_project_user_repo),
) -> list[ProjectUserOut]:
    return [ProjectUserOut.model_validate(pu) for pu in await repo.list_memberships(project_id, user_id)]


@router.post("", response_model=ProjectUserOut, status_code=201)
async def add_project_user(
    body: ProjectUserCreate,
    user: User = Depends(require_roles(UserRole.admin, UserRole.team_lead)),
    repo: ProjectUserRepo = Depends(get_project_user_repo),
) -> ProjectUserOut:
    kwargs = {"project_id": body.project_id, "user_id": body.user_id}
    if body.start_date is not None:
        kwargs["start_date"] = body.start_date
    membership = await repo.add(ProjectUser(**kwargs))
    return ProjectUserOut.model_validate(membership)


@router.patch("/{project_user_id}", response_model=ProjectUserOut)
async def update_project_user(
    project_user_id: uuid.UUID,
    body: ProjectUserUpdate,
    user: User = Depends(require_roles(UserRole.admin, UserRole.team_lead)),
    repo: ProjectUserRepo = Depends(get_project_user_repo),
) -> ProjectUserOut:
    membership = await repo.get(project_user_id)
    if membership is None:
        raise NotFoundError("Project membership not found")
    if body.start_date is not None:
        membership.start_date = body.start_date
    if body.end_date is not None:
        membership.end_date = body.end_date
    await repo.db.flush()
    await repo.db.refresh(membership)
    return ProjectUserOut.model_validate(membership)
