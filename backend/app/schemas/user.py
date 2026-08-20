import uuid
from datetime import datetime

from pydantic import BaseModel, EmailStr

from app.db.models.enums import UserRole


class UserCreate(BaseModel):
    email: EmailStr
    role: UserRole
    organization_id: uuid.UUID | None = None


class UserUpdate(BaseModel):
    role: UserRole | None = None
    organization_id: uuid.UUID | None = None


class UserOut(BaseModel):
    id: uuid.UUID
    email: str
    role: UserRole
    organization_id: uuid.UUID | None = None
    identity_provider: str
    external_sub: str | None = None
    created_at: datetime

    model_config = {"from_attributes": True}
