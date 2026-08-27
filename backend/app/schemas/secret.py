import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel

from app.db.models.enums import SecretAuditStatus, SecretOperation


class SecretProviderInfo(BaseModel):
    name: str
    available: bool


class SecretProviderConfigOut(BaseModel):
    active_provider: str | None
    providers: list[SecretProviderInfo]


class SecretStatusOut(BaseModel):
    """Never carries a secret value -- only whether one resolved successfully."""

    provider: str
    status: Literal["configured", "not_configured", "error"]


class SecretRotateRequest(BaseModel):
    secret_name: str
    tenant: str | None = None


class SecretRotateResponse(BaseModel):
    secret_name: str
    provider: str | None
    status: Literal["rotated", "error"]


class SecretAuditLogOut(BaseModel):
    id: uuid.UUID
    tenant_id: str | None = None
    operation: SecretOperation
    provider: str
    secret_name: str
    user_id: uuid.UUID | None = None
    status: SecretAuditStatus
    created_at: datetime

    model_config = {"from_attributes": True}


class PaginatedSecretAuditLog(BaseModel):
    items: list[SecretAuditLogOut]
    page: int
    page_size: int
    total: int
