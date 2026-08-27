import uuid

from app.core.exceptions import ForbiddenError
from app.db.models.enums import UserRole
from app.db.models.user import User


class RBACService:
    @staticmethod
    def require_role(user: User, *allowed: UserRole) -> None:
        if user.role not in allowed:
            raise ForbiddenError(f"Role '{user.role.value}' is not permitted to perform this action")

    @staticmethod
    def require_same_organization(user: User, organization_id: uuid.UUID | None) -> None:
        if user.role == UserRole.admin:
            return
        if organization_id is None or user.organization_id != organization_id:
            raise ForbiddenError("Not permitted to access this organization's resources")
