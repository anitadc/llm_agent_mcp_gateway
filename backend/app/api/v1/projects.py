import uuid

from fastapi import APIRouter, Depends

from app.api.deps import get_current_user, get_project_repo, require_roles
from app.core.exceptions import NotFoundError
from app.core.logging import get_logger, log_method
from app.db.models.enums import UserRole
from app.db.models.project import Project
from app.db.models.user import User
from app.repositories.project_repo import ProjectRepo
from app.schemas.project import ProjectCreate, ProjectOut, ProjectUpdate

logger = get_logger(__name__)

router = APIRouter(prefix="/v1/projects", tags=["projects"])


@router.get("", response_model=list[ProjectOut])
@log_method(logger)
async def list_projects(
    organization_id: uuid.UUID | None = None,
    user: User = Depends(get_current_user),
    repo: ProjectRepo = Depends(get_project_repo),
) -> list[ProjectOut]:
    scope = organization_id if user.role == UserRole.admin else user.organization_id
    projects = await repo.list_visible(scope)
    logger.info("listing projects", user_id=user.id, organization_id=str(organization_id) if organization_id else None, count=len(projects))
    return [ProjectOut.model_validate(p) for p in projects]


@router.post("", response_model=ProjectOut, status_code=201)
@log_method(logger)
async def create_project(
    body: ProjectCreate,
    user: User = Depends(require_roles(UserRole.admin, UserRole.team_lead)),
    repo: ProjectRepo = Depends(get_project_repo),
) -> ProjectOut:
    logger.info("creating project", user_id=user.id, organization_id=str(body.organization_id), name=body.name)
    project = await repo.add(Project(organization_id=body.organization_id, name=body.name))
    logger.info("project_created", project_id=str(project.id), organization_id=str(body.organization_id))
    return ProjectOut.model_validate(project)


@router.patch("/{project_id}", response_model=ProjectOut)
@log_method(logger)
async def update_project(
    project_id: uuid.UUID,
    body: ProjectUpdate,
    user: User = Depends(require_roles(UserRole.admin, UserRole.team_lead)),
    repo: ProjectRepo = Depends(get_project_repo),
) -> ProjectOut:
    logger.info("updating project", user_id=user.id, project_id=str(project_id), fields=list(body.model_dump(exclude_none=True).keys()))
    project = await repo.get(project_id)
    if project is None:
        raise NotFoundError("Project not found")
    project.name = body.name
    await repo.db.flush()
    await repo.db.refresh(project)
    logger.info("project_updated", project_id=str(project_id))
    return ProjectOut.model_validate(project)
