from app.db.models.organization import Organization
from app.repositories.base import BaseRepository


class OrganizationRepo(BaseRepository[Organization]):
    model = Organization
