from app.db.models.provider_config import ProviderConfig
from app.repositories.base import BaseRepository


class ProviderConfigRepo(BaseRepository[ProviderConfig]):
    model = ProviderConfig
