import uuid
from datetime import datetime

from pydantic import BaseModel


class ApiKeyCreate(BaseModel):
    name: str
    project_id: uuid.UUID
    scopes: list[str] = []


class ApiKeyOut(BaseModel):
    id: uuid.UUID
    project_id: uuid.UUID
    prefix: str
    name: str
    scopes: list[str]
    is_active: bool
    raw_key: str | None = None
    created_at: datetime
    last_used_at: datetime | None = None

    model_config = {"from_attributes": True}
