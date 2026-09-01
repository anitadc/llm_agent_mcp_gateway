import uuid

from app.core.exceptions import ForbiddenError
from app.core.logging import get_logger
from app.db.models.enums import UserRole
from app.db.models.user import User

logger = get_logger(__name__)


class RBACService:
    @staticmethod
    def require_role(user: User, *allowed: UserRole) -> None:
        if user.role not in allowed:
            logger.warning(
                "role_check_failed",
                user_id=str(user.id),
                user_role=user.role.value,
                allowed_roles=[role.value for role in allowed],
            )
            raise ForbiddenError(f"Role '{user.role.value}' is not permitted to perform this action")

    @staticmethod
    def require_same_organization(user: User, organization_id: uuid.UUID | None) -> None:
        if user.role == UserRole.admin:
            return
        if organization_id is None or user.organization_id != organization_id:
            logger.warning(
                "organization_check_failed",
                user_id=str(user.id),
                user_organization_id=str(user.organization_id) if user.organization_id else None,
                requested_organization_id=str(organization_id) if organization_id else None,
            )
            raise ForbiddenError("Not permitted to access this organization's resources")
