import uuid
from typing import Any

from pydantic import BaseModel

from app.db.models.enums import UserRole


class SessionInfo(BaseModel):
    user_id: uuid.UUID
    email: str
    role: UserRole
    organization_id: uuid.UUID | None = None
    # Sourced from the UserIdentity the authenticating IdentityProvider produced
    # for this request -- present whenever the caller authenticated via an
    # Identity Provider (not an API key).
    identity_provider: str | None = None
    tenant_id: str | None = None
    roles: list[str] = []
    groups: list[str] = []
    attributes: dict[str, Any] = {}


class LocalTokenRequest(BaseModel):
    user_id: str
    email: str
    tenant_id: str | None = None
    roles: list[str] = []
    groups: list[str] = []
    expires_seconds: int = 3600


class LocalTokenResponse(BaseModel):
    token: str
    expires_in: int
