import uuid

from fastapi import APIRouter, Depends

from app.api.deps import get_organization_repo, require_roles
from app.core.exceptions import NotFoundError
from app.core.logging import get_logger
from app.db.models.enums import UserRole
from app.db.models.organization import Organization
from app.db.models.user import User
from app.repositories.organization_repo import OrganizationRepo
from app.schemas.organization import OrganizationCreate, OrganizationOut, OrganizationUpdate

router = APIRouter(prefix="/v1/organizations", tags=["organizations"])
logger = get_logger(__name__)


@router.get("", response_model=list[OrganizationOut])
async def list_organizations(
    user: User = Depends(require_roles(UserRole.admin)), repo: OrganizationRepo = Depends(get_organization_repo)
) -> list[OrganizationOut]:
    orgs = await repo.list()
    logger.info("listing organizations", user_id=user.id, count=len(orgs))
    return [OrganizationOut.model_validate(o) for o in orgs]


@router.post("", response_model=OrganizationOut, status_code=201)
async def create_organization(
    body: OrganizationCreate,
    user: User = Depends(require_roles(UserRole.admin)),
    repo: OrganizationRepo = Depends(get_organization_repo),
) -> OrganizationOut:
    logger.info("creating organization", user_id=user.id, name=body.name)
    org = await repo.add(Organization(name=body.name))
    return OrganizationOut.model_validate(org)


@router.patch("/{organization_id}", response_model=OrganizationOut)
async def update_organization(
    organization_id: uuid.UUID,
    body: OrganizationUpdate,
    user: User = Depends(require_roles(UserRole.admin)),
    repo: OrganizationRepo = Depends(get_organization_repo),
) -> OrganizationOut:
    logger.info("updating organization", user_id=user.id, organization_id=str(organization_id), fields=list(body.model_dump(exclude_none=True).keys()))
    org = await repo.get(organization_id)
    if org is None:
        raise NotFoundError("Organization not found")
    org.name = body.name
    await repo.db.flush()
    await repo.db.refresh(org)
    return OrganizationOut.model_validate(org)
