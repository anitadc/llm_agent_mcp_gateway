import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel

from app.db.models.enums import IdentityProviderName


class IdentityProviderInfo(BaseModel):
    name: str
    available: bool


class IdentityProviderConfigOut(BaseModel):
    active_provider: str
    providers: list[IdentityProviderInfo]


class TenantIdentityConfigCreate(BaseModel):
    tenant_id: str
    provider: IdentityProviderName
    issuer: str
    configuration: dict[str, Any] = {}


class TenantIdentityConfigUpdate(BaseModel):
    provider: IdentityProviderName | None = None
    issuer: str | None = None
    configuration: dict[str, Any] | None = None


class TenantIdentityConfigOut(BaseModel):
    id: uuid.UUID
    tenant_id: str
    provider: IdentityProviderName
    issuer: str
    configuration: dict[str, Any]
    created_at: datetime

    model_config = {"from_attributes": True}


class AccessPolicyCreate(BaseModel):
    project_id: uuid.UUID | None = None
    name: str
    allowed_roles: list[str] = []
    allowed_identity_providers: list[str] = []
    allowed_tool_names: list[str] = []
    allowed_agent_keys: list[str] = []
    max_tokens: int | None = None
    is_active: bool = True


class AccessPolicyUpdate(BaseModel):
    allowed_roles: list[str] | None = None
    allowed_identity_providers: list[str] | None = None
    allowed_tool_names: list[str] | None = None
    allowed_agent_keys: list[str] | None = None
    max_tokens: int | None = None
    is_active: bool | None = None


class AccessPolicyOut(BaseModel):
    id: uuid.UUID
    project_id: uuid.UUID | None = None
    name: str
    allowed_roles: list[str]
    allowed_identity_providers: list[str]
    allowed_tool_names: list[str]
    allowed_agent_keys: list[str]
    max_tokens: int | None = None
    is_active: bool
    created_at: datetime

    model_config = {"from_attributes": True}
