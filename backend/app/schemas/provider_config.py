import uuid

from pydantic import BaseModel

from app.db.models.enums import ProviderNameEnum


class ProviderConfigCreate(BaseModel):
    provider: ProviderNameEnum
    display_name: str
    credential_ref: str
    enabled: bool = True


class ProviderConfigUpdate(BaseModel):
    display_name: str | None = None
    credential_ref: str | None = None
    enabled: bool | None = None


class ProviderConfigOut(BaseModel):
    id: uuid.UUID
    provider: ProviderNameEnum
    display_name: str
    credential_ref: str
    enabled: bool

    model_config = {"from_attributes": True}
