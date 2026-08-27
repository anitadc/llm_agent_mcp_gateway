import uuid
from datetime import date

from fastapi import APIRouter, Depends

from app.api.deps import get_current_user, get_request_log_repo
from app.core.logging import get_logger
from app.db.models.enums import RequestStatus
from app.db.models.user import User
from app.repositories.request_log_repo import RequestLogRepo
from app.schemas.log import PaginatedRequestLogs, RequestLogOut

router = APIRouter(prefix="/v1/logs", tags=["logs"])
logger = get_logger(__name__)


@router.get("", response_model=PaginatedRequestLogs)
async def list_request_logs(
    organization_id: uuid.UUID | None = None,
    project_id: uuid.UUID | None = None,
    status: RequestStatus | None = None,
    model_alias: str | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
    page: int = 1,
    page_size: int = 25,
    user: User = Depends(get_current_user),
    repo: RequestLogRepo = Depends(get_request_log_repo),
) -> PaginatedRequestLogs:
    logger.info(
        "listing request logs",
        user_id=user.id,
        organization_id=str(organization_id) if organization_id else None,
        project_id=str(project_id) if project_id else None,
        status=status.value if status else None,
        model_alias=model_alias,
        page=page,
        page_size=page_size,
    )
    items, total = await repo.list_paginated(
        organization_id=organization_id,
        project_id=project_id,
        status=status,
        model_alias=model_alias,
        date_from=date_from,
        date_to=date_to,
        page=page,
        page_size=min(page_size, 100),
    )
    return PaginatedRequestLogs(
        items=[RequestLogOut.model_validate(item) for item in items], page=page, page_size=page_size, total=total
    )
